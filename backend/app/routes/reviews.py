"""Review endpoints for viewing candidate repository diffs."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import models, schemas
from ..auth import SupabaseSession, require_roles
from ..database import get_session
from ..github_app import GitHubAppError, get_github_app_client
from ..services.supabase_memberships import require_org_membership_role
from ..services.llm_service import get_llm_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/candidate-repos", tags=["reviews"])


@router.get("/{repo_id}/diff", response_model=schemas.DiffResponse)
async def get_repo_diff(
    repo_id: str,
    head_branch: str = "main",
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(
        require_roles("authenticated", "service_role")
    ),
) -> schemas.DiffResponse:
    """Fetch diff between seed SHA and candidate's current branch."""
    try:
        repo_uuid = uuid.UUID(repo_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid repository id") from exc

    result = await session.execute(
        select(models.CandidateRepo)
        .options(
            selectinload(models.CandidateRepo.invitation)
            .selectinload(models.Invitation.assessment)
            .selectinload(models.Assessment.org)
            .selectinload(models.Org.github_installation)
        )
        .where(models.CandidateRepo.id == repo_uuid)
    )
    repo = result.scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Verify user has access to this repo's organization
    assessment = repo.invitation.assessment
    if assessment is None:
        raise HTTPException(status_code=500, detail="Repository missing assessment")

    await require_org_membership_role(
        session,
        assessment.org_id,
        current_session,
        allowed_roles=("owner", "admin", "viewer"),
    )

    # Get GitHub App client for this org
    org = assessment.org
    if org is None:
        raise HTTPException(status_code=500, detail="Assessment missing organization")

    github_installation = org.github_installation
    if github_installation is None or github_installation.installation_id is None:
        raise HTTPException(
            status_code=400,
            detail="GitHub App not connected for this organization",
        )

    github_app = get_github_app_client()
    github = github_app.with_installation(
        github_installation.installation_id, github_installation.account_login or ""
    )

    # Fetch diff from GitHub API
    base_sha = repo.seed_sha_pinned
    repo_full_name = repo.repo_full_name

    try:
        token = await github._get_cached_installation_token()
        async with github._build_client(token=token) as client:
            # Get repository info to determine default branch
            repo_response = await github._request(
                client,
                "GET",
                f"/repos/{repo_full_name}",
                token=token,
                expected_status=[200],
            )
            repo_info = repo_response.json()
            default_branch = repo_info.get("default_branch", "main")
            
            commits_response = await github._request(
                client,
                "GET",
                f"/repos/{repo_full_name}/commits?sha={head_branch}&per_page=100",
                token=token,
                expected_status=[200],
            )
            commits = commits_response.json()
            
            if not commits or len(commits) == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Repository has no commits to compare",
                )
            
            first_commit = commits[-1]
            first_sha = first_commit.get("sha")
            
            if not first_sha:
                raise HTTPException(
                    status_code=404,
                    detail="Could not determine first commit SHA",
                )
            
            compare_url = f"/repos/{repo_full_name}/compare/{first_sha}...{head_branch}"
            
            try:
                response = await github._request(
                    client,
                    "GET",
                    compare_url,
                    token=token,
                    expected_status=[200, 404],
                )
                
                if response.status_code == 404:

                    compare_url = f"/repos/{repo_full_name}/compare/{head_branch}...{first_sha}"
                    response = await github._request(
                        client,
                        "GET",
                        compare_url,
                        token=token,
                        expected_status=[200, 404],
                    )
                    
                    if response.status_code == 404:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Could not compare repository: branch {head_branch} or commit {first_sha} not found",
                        )
                        
            except HTTPException:
                raise
            except Exception as exc:
                if "404" in str(exc) or "Not Found" in str(exc):
                    raise HTTPException(
                        status_code=404,
                        detail=f"Could not compare repository: {str(exc)}",
                    ) from exc
                raise

            compare_data = response.json()
                
    except HTTPException:
        raise
    except GitHubAppError as exc:
        # Check if it's a 404 from GitHub
        if "404" in str(exc) or "Not Found" in str(exc):
            raise HTTPException(
                status_code=404,
                detail=f"Repository or branch not found: {repo_full_name}",
            ) from exc
        raise HTTPException(status_code=502, detail=f"GitHub API error: {str(exc)}") from exc
    except Exception as exc:
        # Handle httpx.HTTPStatusError and other exceptions from GitHub API
        error_msg = str(exc)
        # Check if it's a 404 or Not Found error
        if "404" in error_msg or "Not Found" in error_msg or (hasattr(exc, "response") and exc.response and exc.response.status_code == 404):
            raise HTTPException(
                status_code=404,
                detail=f"Repository or branch not found: {repo_full_name}",
            ) from exc
        # Check if it's a 500 error from GitHub (temporary server issue)
        if "500" in error_msg or (hasattr(exc, "response") and exc.response and exc.response.status_code == 500):
            raise HTTPException(
                status_code=503,
                detail=f"GitHub API temporarily unavailable. Please try again later.",
            ) from exc
        # Generic error handler
        raise HTTPException(status_code=502, detail=f"GitHub API error: {error_msg}") from exc

    # Parse GitHub API response
    base_commit = compare_data.get("base_commit", {})
    head_commit = compare_data.get("merge_base_commit") or compare_data.get("head_commit", {})
    
    base_sha_from_api = base_commit.get("sha") if isinstance(base_commit, dict) else head_branch
    head_sha_from_api = (
        head_commit.get("sha") if isinstance(head_commit, dict) else None
    ) or head_branch

    files = []
    total_additions = 0
    total_deletions = 0
    
    for file_data in compare_data.get("files", []):
        status = "modified"
        if file_data.get("status") == "added":
            status = "added"
        elif file_data.get("status") == "removed":
            status = "removed"
        elif file_data.get("status") == "renamed":
            status = "renamed"

        file_additions = file_data.get("additions", 0)
        file_deletions = file_data.get("deletions", 0)
        total_additions += file_additions
        total_deletions += file_deletions

        patch = file_data.get("patch")
        if patch:
            filename = file_data.get("filename", "")
            previous_filename = file_data.get("previous_filename") or filename

            if not patch.startswith("diff --git"):
                old_path = previous_filename if status != "added" else "/dev/null"
                new_path = filename if status != "removed" else "/dev/null"

                if "\n--- " not in patch:
                    patch = f"diff --git a/{old_path} b/{new_path}\n--- a/{old_path}\n+++ b/{new_path}\n{patch}"
                else:
                    patch = f"diff --git a/{old_path} b/{new_path}\n{patch}"

        files.append(
            schemas.DiffFile(
                filename=file_data.get("filename", ""),
                status=status,
                additions=file_additions,
                deletions=file_deletions,
                changes=file_data.get("changes", 0),
                patch=patch,
                blobUrl=file_data.get("blob_url"),
                previousFilename=file_data.get("previous_filename"),
            )
        )

    commits = []
    for commit_data in compare_data.get("commits", []):
        commit_info = commit_data.get("commit", {})
        author_info = commit_info.get("author", {})
        commits.append(
            schemas.DiffCommit(
                sha=commit_data.get("sha", "")[:7],
                message=commit_info.get("message", "").split("\n")[0],
                author=author_info.get("name", "Unknown"),
                date=datetime.fromisoformat(
                    author_info.get("date", "").replace("Z", "+00:00")
                ).replace(tzinfo=timezone.utc),
            )
        )

    html_url = compare_data.get("html_url")

    return schemas.DiffResponse(
        files=files,
        totalAdditions=total_additions,
        totalDeletions=total_deletions,
        totalChanges=compare_data.get("total_commits", 0),
        commits=commits,
        baseSha=base_sha_from_api,
        headSha=head_sha_from_api,
        htmlUrl=html_url,
    )


# Helper function to verify invitation access
async def _get_invitation_and_verify_access(
    invitation_id: uuid.UUID,
    session: AsyncSession,
    current_session: SupabaseSession,
    allowed_roles: tuple[str, ...] = ("owner", "admin", "viewer"),
    load_candidate_repo: bool = False,
    load_github_installation: bool = False,
) -> models.Invitation:
    """Helper to get invitation and verify user has access."""
    # Build the base query with assessment and org
    org_load = selectinload(models.Invitation.assessment).selectinload(models.Assessment.org)
    
    # If we need github_installation, add it to the chain
    if load_github_installation:
        org_load = org_load.selectinload(models.Org.github_installation)
    
    query = select(models.Invitation).options(org_load)
    
    if load_candidate_repo:
        query = query.options(selectinload(models.Invitation.candidate_repo))
    
    result = await session.execute(query.where(models.Invitation.id == invitation_id))
    invitation = result.scalar_one_or_none()
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found")

    assessment = invitation.assessment
    if assessment is None:
        raise HTTPException(status_code=500, detail="Invitation missing assessment")

    await require_org_membership_role(
        session,
        assessment.org_id,
        current_session,
        allowed_roles=allowed_roles,
    )
    return invitation


# Helper function to get or create ReviewFeedback for an invitation
async def _get_or_create_review_feedback(
    invitation_id: uuid.UUID,
    session: AsyncSession,
    created_by: uuid.UUID | None = None,
) -> models.ReviewFeedback:
    """Get the most recent ReviewFeedback record for an invitation, or create a new one."""
    result = await session.execute(
        select(models.ReviewFeedback)
        .where(models.ReviewFeedback.invitation_id == invitation_id)
        .order_by(models.ReviewFeedback.created_at.desc())
        .limit(1)
    )
    feedback = result.scalar_one_or_none()
    
    if feedback is None:
        feedback = models.ReviewFeedback(
            invitation_id=invitation_id,
            created_by=created_by,
        )
        session.add(feedback)
        # Don't flush here - let the commit in the calling function handle it
        # Flushing here causes issues with foreign key validation for users table
    
    return feedback


# Helper function to calculate score summary
async def _calculate_score_summary(
    invitation: models.Invitation,
    assessment_id: uuid.UUID,
    session: AsyncSession,
    store_in_db: bool = True,
    created_by: uuid.UUID | None = None,
) -> schemas.ReviewScoreSummary:
    """Calculate score summary for an invitation and optionally store it in the database."""
    # Get all features for the assessment
    features_result = await session.execute(
        select(models.AssessmentFeature).where(
            models.AssessmentFeature.assessment_id == assessment_id
        ).order_by(models.AssessmentFeature.weight.desc(), models.AssessmentFeature.name)
    )
    features = features_result.scalars().all()

    # Get all scores for the invitation (both checked and unchecked)
    scores_result = await session.execute(
        select(models.ReviewFeatureScore).where(
            models.ReviewFeatureScore.invitation_id == invitation.id,
        )
    )
    all_scores = scores_result.scalars().all()
    # Only include checked features in the set
    checked_feature_ids = {score.feature_id for score in all_scores if score.checked}

    # Calculate totals
    total_score = 0.0
    max_score = 0.0
    feature_details = []

    for feature in features:
        weight = float(feature.weight)
        max_score += weight
        is_checked = feature.id in checked_feature_ids
        feature_score = weight if is_checked else 0.0
        total_score += feature_score

        feature_details.append({
            "feature_id": str(feature.id),
            "name": feature.name,
            "weight": weight,
            "checked": is_checked,
            "score": feature_score,
        })

    percentage = (total_score / max_score * 100) if max_score > 0 else 0.0
    
    # Round to 2 decimal places
    # Ensure we always return valid numbers (at least 0)
    total_score_rounded = round(float(total_score), 2)
    max_score_rounded = round(float(max_score), 2)
    percentage_rounded = round(float(percentage), 2)

    # Store in database if requested
    if store_in_db:
        feedback = await _get_or_create_review_feedback(
            invitation.id,
            session,
            created_by=created_by,
        )
        feedback.calculated_score = total_score_rounded
        feedback.max_score = max_score_rounded
        if not feedback.created_by and created_by:
            feedback.created_by = created_by
        # Don't flush here - let the commit in the calling function handle it
        # This avoids foreign key validation issues during flush

    return schemas.ReviewScoreSummary(
        invitation_id=invitation.id,
        total_score=total_score_rounded,
        max_score=max_score_rounded,
        percentage=percentage_rounded,
        features=feature_details,
    )


@router.post("/invitations/{invitation_id}/features/{feature_id}/toggle", response_model=schemas.ReviewScoreSummary)
async def toggle_feature_score(
    invitation_id: str,
    feature_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> schemas.ReviewScoreSummary:
    """
    Toggle a feature score (check/uncheck) for an invitation.
    Returns the updated score summary.
    """
    try:
        invitation_uuid = uuid.UUID(invitation_id)
        feature_uuid = uuid.UUID(feature_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid id") from exc

    # Verify invitation exists and user has access
    invitation = await _get_invitation_and_verify_access(
        invitation_uuid, session, current_session, allowed_roles=("owner", "admin", "viewer")
    )

    # Store assessment_id before any commits that might expire the object
    assessment_id = invitation.assessment_id

    # Verify feature belongs to the invitation's assessment
    feature_result = await session.execute(
        select(models.AssessmentFeature).where(
            models.AssessmentFeature.id == feature_uuid,
            models.AssessmentFeature.assessment_id == assessment_id,
        )
    )
    feature = feature_result.scalar_one_or_none()
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail="Feature not found or does not belong to this assessment",
        )

    # Get or create score record
    score_result = await session.execute(
        select(models.ReviewFeatureScore).where(
            models.ReviewFeatureScore.invitation_id == invitation_uuid,
            models.ReviewFeatureScore.feature_id == feature_uuid,
        )
    )
    score = score_result.scalar_one_or_none()

    if score:
        # Toggle existing score
        score.checked = not score.checked
        if not score.created_by:
            score.created_by = current_session.user.id if current_session.user else None
    else:
        # Create new score (initially checked)
        score = models.ReviewFeatureScore(
            invitation_id=invitation_uuid,
            feature_id=feature_uuid,
            checked=True,
            created_by=current_session.user.id if current_session.user else None,
        )
        session.add(score)

    await session.flush()

    # Calculate score summary and store it in the database
    created_by_uuid = current_session.user.id if current_session.user else None
    summary = await _calculate_score_summary(
        invitation, 
        assessment_id, 
        session, 
        store_in_db=True,
        created_by=created_by_uuid,
    )
    
    await session.commit()
    
    return summary


@router.get("/invitations/{invitation_id}/score-summary", response_model=schemas.ReviewScoreSummary)
async def get_review_score_summary(
    invitation_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> schemas.ReviewScoreSummary:
    """Get current score summary for an invitation."""
    try:
        invitation_uuid = uuid.UUID(invitation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid invitation id") from exc

    # Verify invitation exists and user has access
    invitation = await _get_invitation_and_verify_access(
        invitation_uuid, session, current_session, allowed_roles=("owner", "admin", "viewer")
    )

    # Store assessment_id
    assessment_id = invitation.assessment_id

    # Always recalculate to ensure accuracy and get the feature breakdown
    # The calculation will update the stored values in review_feedback
    created_by_uuid = current_session.user.id if current_session.user else None
    summary = await _calculate_score_summary(
        invitation, 
        assessment_id, 
        session, 
        store_in_db=True,
        created_by=created_by_uuid,
    )
    
    await session.commit()
    
    return summary



# Helper function to get diff data formatted for LLM
async def _get_diff_data_for_llm(
    invitation: models.Invitation,
    session: AsyncSession,
) -> tuple[str, str]:
    """Get formatted diff data for LLM consumption.
    
    Returns:
        tuple of (file_summary, diff_text)
    """
    repo = invitation.candidate_repo
    if repo is None:
        raise HTTPException(
            status_code=404,
            detail="No repository found for this invitation. Candidate must start the assessment first.",
        )
    
    # Fetch diff using the existing logic
    assessment = invitation.assessment
    if assessment is None:
        raise HTTPException(status_code=500, detail="Invitation missing assessment")
    
    org = assessment.org
    if org is None:
        raise HTTPException(status_code=500, detail="Assessment missing organization")
    
    github_installation = org.github_installation
    if github_installation is None or github_installation.installation_id is None:
        raise HTTPException(
            status_code=400,
            detail="GitHub App not connected for this organization",
        )
    
    github_app = get_github_app_client()
    github = github_app.with_installation(
        github_installation.installation_id, github_installation.account_login or ""
    )
    
    repo_full_name = repo.repo_full_name
    head_branch = "main"
    
    try:
        token = await github._get_cached_installation_token()
        async with github._build_client(token=token) as client:
            commits_response = await github._request(
                client,
                "GET",
                f"/repos/{repo_full_name}/commits?sha={head_branch}&per_page=100",
                token=token,
                expected_status=[200],
            )
            commits = commits_response.json()
            
            if not commits or len(commits) == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Repository has no commits to compare",
                )
            
            first_commit = commits[-1]
            first_sha = first_commit.get("sha")
            
            if not first_sha:
                raise HTTPException(
                    status_code=404,
                    detail="Could not determine first commit SHA",
                )
            
            compare_url = f"/repos/{repo_full_name}/compare/{first_sha}...{head_branch}"
            
            response = await github._request(
                client,
                "GET",
                compare_url,
                token=token,
                expected_status=[200, 404],
            )
            
            if response.status_code == 404:
                compare_url = f"/repos/{repo_full_name}/compare/{head_branch}...{first_sha}"
                response = await github._request(
                    client,
                    "GET",
                    compare_url,
                    token=token,
                    expected_status=[200, 404],
                )
                
                if response.status_code == 404:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Could not compare repository: branch {head_branch} or commit {first_sha} not found",
                    )
            
            compare_data = response.json()
            
    except HTTPException:
        raise
    except GitHubAppError as exc:
        if "404" in str(exc) or "Not Found" in str(exc):
            raise HTTPException(
                status_code=404,
                detail=f"Repository or branch not found: {repo_full_name}",
            ) from exc
        raise HTTPException(status_code=502, detail=f"GitHub API error: {str(exc)}") from exc
    except Exception as exc:
        error_msg = str(exc)
        if "404" in error_msg or "Not Found" in error_msg:
            raise HTTPException(
                status_code=404,
                detail=f"Repository or branch not found: {repo_full_name}",
            ) from exc
        raise HTTPException(status_code=502, detail=f"GitHub API error: {error_msg}") from exc
    
    # Format files for LLM
    files = compare_data.get("files", [])
    
    # Create file summary
    file_summary_lines = []
    for file_data in files:
        status = file_data.get("status", "modified")
        filename = file_data.get("filename", "")
        additions = file_data.get("additions", 0)
        deletions = file_data.get("deletions", 0)
        file_summary_lines.append(f"- {status}: {filename} (+{additions}/-{deletions} lines)")
    
    file_summary = "\n".join(file_summary_lines) if file_summary_lines else "No file changes."
    
    # Create detailed diff text (truncate if too long)
    MAX_DIFF_LENGTH = 50000  # Limit to ~50k characters to stay within token limits
    diff_parts = []
    current_length = 0
    
    for file_data in files:
        filename = file_data.get("filename", "")
        status = file_data.get("status", "modified")
        patch = file_data.get("patch", "")
        
        if patch:
            file_header = f"\n--- File: {filename} ({status}) ---\n"
            file_content = file_header + patch
            
            if current_length + len(file_content) > MAX_DIFF_LENGTH:
                # Truncate and add note
                remaining = MAX_DIFF_LENGTH - current_length - len(file_header) - 100
                if remaining > 0:
                    diff_parts.append(file_header + patch[:remaining] + "\n... (truncated)")
                diff_parts.append(f"\n--- Note: Additional file changes truncated due to length limits ---")
                break
            
            diff_parts.append(file_content)
            current_length += len(file_content)
    
    diff_text = "\n".join(diff_parts) if diff_parts else "No diff content available."
    
    return file_summary, diff_text


@router.get("/invitations/{invitation_id}/llm-analysis", response_model=schemas.ReviewLLMAnalysisRead)
async def get_llm_analysis(
    invitation_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> schemas.ReviewLLMAnalysisRead:
    """Get existing LLM analysis for an invitation."""
    try:
        invitation_uuid = uuid.UUID(invitation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid invitation id") from exc
    
    # Verify invitation exists and user has access
    invitation = await _get_invitation_and_verify_access(
        invitation_uuid, session, current_session, allowed_roles=("owner", "admin", "viewer")
    )
    
    # Fetch analysis
    result = await session.execute(
        select(models.ReviewLLMAnalysis)
        .where(models.ReviewLLMAnalysis.invitation_id == invitation_uuid)
    )
    analysis = result.scalar_one_or_none()
    
    if analysis is None:
        raise HTTPException(status_code=404, detail="No LLM analysis found for this invitation")
    
    return schemas.ReviewLLMAnalysisRead(
        id=str(analysis.id),
        invitation_id=str(analysis.invitation_id),
        analysis_text=analysis.analysis_text,
        model_used=analysis.model_used,
        prompt_version=analysis.prompt_version,
        created_at=analysis.created_at,
        created_by=str(analysis.created_by) if analysis.created_by else None,
    )


@router.post("/invitations/{invitation_id}/llm-analysis/generate", response_model=schemas.ReviewLLMAnalysisRead)
async def generate_llm_analysis(
    invitation_id: str,
    payload: schemas.ReviewLLMAnalysisCreate,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> schemas.ReviewLLMAnalysisRead:
    """Generate or regenerate LLM analysis for an invitation."""
    logger.info(f"📥 Received LLM analysis generation request for invitation {invitation_id}, regenerate={payload.regenerate}")
    
    try:
        invitation_uuid = uuid.UUID(invitation_id)
        logger.debug(f"✅ Parsed invitation UUID: {invitation_uuid}")
    except ValueError as exc:
        logger.error(f"❌ Invalid invitation ID format: {invitation_id}")
        raise HTTPException(status_code=400, detail="Invalid invitation id") from exc
    
    # Verify invitation exists and user has access
    # Load candidate_repo and github_installation since _get_diff_data_for_llm needs them
    invitation = await _get_invitation_and_verify_access(
        invitation_uuid, session, current_session, allowed_roles=("owner", "admin", "viewer"), load_candidate_repo=True, load_github_installation=True
    )
    
    # Get assessment and rubric (REQUIRED)
    assessment = invitation.assessment
    if assessment is None:
        raise HTTPException(status_code=500, detail="Invitation missing assessment")
    
    rubric_text = assessment.rubric_text
    if not rubric_text:
        raise HTTPException(
            status_code=400,
            detail="Assessment does not have a rubric. Please add a rubric to the assessment before generating LLM analysis.",
        )
    
    # Delete existing analysis if regenerating
    if payload.regenerate:
        logger.info(f"🔄 Regenerating analysis - deleting existing analysis for invitation {invitation_id}")
        result = await session.execute(
            select(models.ReviewLLMAnalysis)
            .where(models.ReviewLLMAnalysis.invitation_id == invitation_uuid)
        )
        existing = result.scalar_one_or_none()
        if existing:
            session.delete(existing)  # delete() is synchronous, not async
            await session.flush()
            logger.info(f"✅ Deleted existing analysis")
    
    # Get diff data
    logger.info(f"🚀 Starting LLM analysis generation for invitation {invitation_id}")
    logger.debug(f"📋 Rubric text length: {len(rubric_text)} chars")
    
    try:
        logger.debug("📥 Fetching diff data from repository...")
        file_summary, diff_text = await _get_diff_data_for_llm(invitation, session)
        logger.info(f"✅ Diff data fetched. Summary: {len(file_summary)} chars, Diff: {len(diff_text)} chars")
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as exc:
        logger.error("❌ Failed to get diff data for LLM: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch repository diff: {str(exc)}",
        ) from exc
    
    # Get LLM provider and generate analysis
    try:
        logger.debug("🔧 Initializing LLM provider...")
        llm_provider = get_llm_provider()
        logger.info("✅ LLM provider initialized successfully")
    except ValueError as exc:
        # Likely missing API key or invalid configuration
        logger.error("❌ LLM provider configuration error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"LLM service configuration error: {str(exc)}. Please check your OPENAI_API_KEY environment variable.",
        ) from exc
    
    try:
        logger.info("🤖 Calling LLM to generate analysis...")
        result = await llm_provider.generate_analysis(
            rubric=rubric_text,
            diff_text=diff_text,
            file_summary=file_summary,
        )
        logger.info(f"✅ LLM analysis generated successfully. Result length: {len(result.get('text', ''))} chars")
    except Exception as exc:
        # Log the full exception for debugging
        logger.error("❌ Failed to generate LLM analysis: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate LLM analysis: {str(exc)}. Please check your LLM API configuration and try again.",
        ) from exc
    
    # Store result in database
    created_by_uuid = current_session.user.id if current_session.user else None
    
    try:
        # Defensive check: ensure invitation_uuid is not None
        if invitation_uuid is None:
            raise HTTPException(
                status_code=400,
                detail="Invalid invitation ID: None",
            )
        
        # Verify invitation still exists before updating (prevent race conditions with deletes)
        invitation_check = await session.get(models.Invitation, invitation_uuid)
        if invitation_check is None:
            raise HTTPException(
                status_code=404,
                detail="Invitation not found. It may have been deleted.",
            )
        
        # Check if analysis already exists (shouldn't happen if regenerate=True, but handle edge case)
        result_query = await session.execute(
            select(models.ReviewLLMAnalysis)
            .where(models.ReviewLLMAnalysis.invitation_id == invitation_uuid)
        )
        existing_analysis = result_query.scalar_one_or_none()
        
        if existing_analysis:
            # Verify the existing analysis has a valid invitation_id
            if existing_analysis.invitation_id is None:
                logger.warning(f"⚠️ Existing analysis {existing_analysis.id} has null invitation_id, fixing it")
                existing_analysis.invitation_id = invitation_uuid
            
            # Update existing - use update() to avoid relationship issues
            await session.execute(
                update(models.ReviewLLMAnalysis)
                .where(models.ReviewLLMAnalysis.id == existing_analysis.id)
                .values(
                    invitation_id=invitation_uuid,  # Explicitly set to prevent null
                    analysis_text=result["text"],
                    model_used=result["model"],
                    prompt_version="v1.0",
                    raw_response=result,
                    updated_at=func.now(),
                )
            )
            # Update created_by separately if needed
            if not existing_analysis.created_by and created_by_uuid:
                await session.execute(
                    update(models.ReviewLLMAnalysis)
                    .where(models.ReviewLLMAnalysis.id == existing_analysis.id)
                    .values(created_by=created_by_uuid)
                )
            
            # Refresh to get updated object
            await session.refresh(existing_analysis)
            analysis = existing_analysis
        else:
            # Create new
            analysis = models.ReviewLLMAnalysis(
                invitation_id=invitation_uuid,
                analysis_text=result["text"],
                model_used=result["model"],
                prompt_version="v1.0",
                raw_response=result,
                created_by=created_by_uuid,
            )
            session.add(analysis)
        
        await session.commit()
        await session.refresh(analysis)
    except Exception as exc:
        logger.error("❌ Failed to save LLM analysis to database: %s", exc, exc_info=True)
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save analysis to database: {str(exc)}",
        ) from exc
    
    return schemas.ReviewLLMAnalysisRead(
        id=str(analysis.id),
        invitation_id=str(analysis.invitation_id),
        analysis_text=analysis.analysis_text,
        model_used=analysis.model_used,
        prompt_version=analysis.prompt_version,
        created_at=analysis.created_at,
        created_by=str(analysis.created_by) if analysis.created_by else None,
    )


@router.get("/invitations/{invitation_id}/llm-conversation", response_model=list[schemas.LLMConversationMessageRead])
async def get_conversation_history(
    invitation_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> list[schemas.LLMConversationMessageRead]:
    """Get conversation history for an invitation."""
    try:
        invitation_uuid = uuid.UUID(invitation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid invitation id") from exc
    
    # Verify invitation exists and user has access
    invitation = await _get_invitation_and_verify_access(
        invitation_uuid, session, current_session, allowed_roles=("owner", "admin", "viewer")
    )
    
    # Fetch conversation history ordered by created_at
    result = await session.execute(
        select(models.ReviewLLMConversation)
        .where(models.ReviewLLMConversation.invitation_id == invitation_uuid)
        .order_by(models.ReviewLLMConversation.created_at)
    )
    messages = result.scalars().all()
    
    return [
        schemas.LLMConversationMessageRead(
            id=str(msg.id),
            invitation_id=str(msg.invitation_id),
            message_type=msg.message_type,
            message_text=msg.message_text,
            model_used=msg.model_used,
            created_at=msg.created_at,
            created_by=str(msg.created_by) if msg.created_by else None,
        )
        for msg in messages
    ]


@router.post("/invitations/{invitation_id}/llm-conversation/ask", response_model=schemas.LLMConversationMessageRead)
async def ask_question(
    invitation_id: str,
    payload: schemas.LLMQuestionCreate,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> schemas.LLMConversationMessageRead:
    """Ask a question about the codebase with full context (rubric + diffs + history)."""
    try:
        invitation_uuid = uuid.UUID(invitation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid invitation id") from exc
    
    # Verify invitation exists and user has access
    # Load candidate_repo and github_installation since _get_diff_data_for_llm needs them
    invitation = await _get_invitation_and_verify_access(
        invitation_uuid, session, current_session, allowed_roles=("owner", "admin", "viewer"), load_candidate_repo=True, load_github_installation=True
    )
    
    # Get assessment and rubric (REQUIRED)
    assessment = invitation.assessment
    if assessment is None:
        raise HTTPException(status_code=500, detail="Invitation missing assessment")
    
    rubric_text = assessment.rubric_text
    if not rubric_text:
        raise HTTPException(
            status_code=400,
            detail="Assessment does not have a rubric. Please add a rubric to the assessment before asking questions.",
        )
    
    # Get diff data
    file_summary, diff_text = await _get_diff_data_for_llm(invitation, session)
    
    # Get initial analysis if it exists
    analysis_result = await session.execute(
        select(models.ReviewLLMAnalysis)
        .where(models.ReviewLLMAnalysis.invitation_id == invitation_uuid)
    )
    initial_analysis_model = analysis_result.scalar_one_or_none()
    initial_analysis_text = initial_analysis_model.analysis_text if initial_analysis_model else None
    
    # Get conversation history
    history_result = await session.execute(
        select(models.ReviewLLMConversation)
        .where(models.ReviewLLMConversation.invitation_id == invitation_uuid)
        .order_by(models.ReviewLLMConversation.created_at)
    )
    history_messages = history_result.scalars().all()
    
    # Format conversation history for LLM
    conversation_history = []
    for msg in history_messages:
        conversation_history.append({
            "role": msg.message_type,  # "user" or "assistant"
            "content": msg.message_text,
        })
    
    # Store user question
    created_by_uuid = current_session.user.id if current_session.user else None
    user_message = models.ReviewLLMConversation(
        invitation_id=invitation_uuid,
        message_type="user",
        message_text=payload.question,
        created_by=created_by_uuid,
    )
    session.add(user_message)
    await session.flush()
    
    # Get LLM provider and generate response
    llm_provider = get_llm_provider()
    result = await llm_provider.answer_question(
        rubric=rubric_text,
        diff_text=diff_text,
        file_summary=file_summary,
        question=payload.question,
        conversation_history=conversation_history,
        initial_analysis=initial_analysis_text,
    )
    
    # Store assistant response
    assistant_message = models.ReviewLLMConversation(
        invitation_id=invitation_uuid,
        message_type="assistant",
        message_text=result["text"],
        model_used=result["model"],
        context_snapshot={
            "rubric_length": len(rubric_text),
            "diff_length": len(diff_text),
            "has_initial_analysis": initial_analysis_text is not None,
            "conversation_length": len(conversation_history),
        },
        created_by=created_by_uuid,
    )
    session.add(assistant_message)
    
    await session.commit()
    await session.refresh(assistant_message)
    
    return schemas.LLMConversationMessageRead(
        id=str(assistant_message.id),
        invitation_id=str(assistant_message.invitation_id),
        message_type=assistant_message.message_type,
        message_text=assistant_message.message_text,
        model_used=assistant_message.model_used,
        created_at=assistant_message.created_at,
        created_by=str(assistant_message.created_by) if assistant_message.created_by else None,
    )
