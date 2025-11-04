"""Assessment endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import models, schemas
from ..auth import SupabaseSession, require_roles
from ..database import get_session
from ..services.supabase_memberships import require_org_membership_role

router = APIRouter(prefix="/api/assessments", tags=["assessments"])


@router.post("", response_model=schemas.AssessmentRead, status_code=201)
async def create_assessment(
    payload: schemas.AssessmentCreate,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> schemas.AssessmentRead:
    org_id = payload.org_id
    seed_id = payload.seed_id

    org_result = await session.execute(select(models.Org).where(models.Org.id == org_id))
    if org_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    seed_result = await session.execute(
        select(models.Seed).where(models.Seed.id == seed_id, models.Seed.org_id == org_id)
    )
    seed = seed_result.scalar_one_or_none()
    if seed is None:
        raise HTTPException(status_code=404, detail="Seed not found for this organization")

    await require_org_membership_role(
        session,
        org_id,
        current_session,
        allowed_roles=("owner", "admin"),
    )

    assessment = models.Assessment(
        org_id=org_id,
        seed_id=seed_id,
        title=payload.title,
        description=payload.description,
        instructions=payload.instructions,
        candidate_email_subject=payload.candidate_email_subject,
        candidate_email_body=payload.candidate_email_body,
        time_to_start=payload.time_to_start,
        time_to_complete=payload.time_to_complete,
        created_by=payload.created_by if payload.created_by else current_session.user.id,
        rubric_text=payload.rubric_text,
        sort_mode=payload.sort_mode or "auto",
    )
    session.add(assessment)
    await session.commit()
    await session.refresh(assessment)
    return schemas.AssessmentRead.from_orm(assessment)


@router.get("/{assessment_id}", response_model=schemas.AssessmentRead)
async def get_assessment(
    assessment_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(
        require_roles("owner", "admin", "viewer", "service_role")
    ),
) -> schemas.AssessmentRead:
    try:
        assessment_uuid = uuid.UUID(assessment_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid assessment id") from exc

    result = await session.execute(
        select(models.Assessment).where(models.Assessment.id == assessment_uuid)
    )
    assessment = result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    
    await require_org_membership_role(
        session,
        assessment.org_id,
        current_session,
        allowed_roles=("owner", "admin", "viewer"),
    )
    return schemas.AssessmentRead.from_orm(assessment)


@router.patch("/{assessment_id}", response_model=schemas.AssessmentRead)
async def update_assessment(
    assessment_id: str,
    payload: schemas.AssessmentUpdate,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> schemas.AssessmentRead:
    """Update an assessment."""
    try:
        assessment_uuid = uuid.UUID(assessment_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid assessment id") from exc

    result = await session.execute(
        select(models.Assessment).where(models.Assessment.id == assessment_uuid)
    )
    assessment = result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    await require_org_membership_role(
        session,
        assessment.org_id,
        current_session,
        allowed_roles=("owner", "admin"),
    )

    # Update fields if provided
    if payload.rubric_text is not None:
        assessment.rubric_text = payload.rubric_text
    
    if payload.sort_mode is not None:
        if payload.sort_mode not in ("auto", "manual"):
            raise HTTPException(
                status_code=400, detail="sort_mode must be 'auto' or 'manual'"
            )
        assessment.sort_mode = payload.sort_mode

    await session.commit()
    await session.refresh(assessment)
    return schemas.AssessmentRead.from_orm(assessment)


@router.delete("/{assessment_id}", status_code=204)
async def delete_assessment(
    assessment_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> None:
    """
    Delete an assessment permanently.
    
    This will cascade delete:
    - All invitations (which cascade to review_feedback, review_comments, submissions, candidate_repos, access_tokens)
    - All assessment_features (which cascade to review_feature_scores via feature_id)
    - All review_feature_scores (also cascade from invitations via invitation_id)
    """
    try:
        assessment_uuid = uuid.UUID(assessment_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid assessment id") from exc

    result = await session.execute(
        select(models.Assessment).where(models.Assessment.id == assessment_uuid)
    )
    assessment = result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    await require_org_membership_role(
        session,
        assessment.org_id,
        current_session,
        allowed_roles=("owner", "admin"),
    )

    # Delete the assessment - CASCADE will handle all related data:
    # - invitations -> review_feedback, review_comments, submissions, candidate_repos, access_tokens
    # - assessment_features -> review_feature_scores (via feature_id)
    # - invitations -> review_feature_scores (via invitation_id)
    await session.delete(assessment)
    await session.commit()


@router.get("/{assessment_id}/invitation-scores", response_model=list[schemas.InvitationScoreSummary])
async def get_assessment_invitation_scores(
    assessment_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(
        require_roles("authenticated", "service_role", "owner", "admin", "viewer")
    ),
) -> list[schemas.InvitationScoreSummary]:
    """Get score summaries for all invitations in an assessment."""
    try:
        assessment_uuid = uuid.UUID(assessment_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid assessment id") from exc

    result = await session.execute(
        select(models.Assessment)
        .options(
            selectinload(models.Assessment.invitations),
            selectinload(models.Assessment.features),
        )
        .where(models.Assessment.id == assessment_uuid)
    )
    assessment = result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    await require_org_membership_role(
        session,
        assessment.org_id,
        current_session,
        allowed_roles=("owner", "admin", "viewer"),
    )

    # Get all features for the assessment
    features = assessment.features or []
    features_list = sorted(features, key=lambda f: (-f.weight, f.name))
    max_score = sum(float(f.weight) for f in features_list) if features_list else 0.0

    # Get all invitations for this assessment
    invitations = assessment.invitations or []

    if not invitations:
        return []

    # Get all stored scores from review_feedback for all invitations
    invitation_ids = [inv.id for inv in invitations]
    feedback_result = await session.execute(
        select(models.ReviewFeedback).where(
            models.ReviewFeedback.invitation_id.in_(invitation_ids)
        )
    )
    all_feedback = feedback_result.scalars().all()

    # Group feedback by invitation_id (use most recent if multiple exist)
    feedback_by_invitation: dict[uuid.UUID, models.ReviewFeedback] = {}
    for feedback in all_feedback:
        # Keep the most recent feedback for each invitation
        if feedback.invitation_id not in feedback_by_invitation:
            feedback_by_invitation[feedback.invitation_id] = feedback
        elif feedback.created_at > feedback_by_invitation[feedback.invitation_id].created_at:
            feedback_by_invitation[feedback.invitation_id] = feedback

    # Build score summaries from stored feedback or calculate if not available
    invitation_scores = []
    for invitation in invitations:
        feedback = feedback_by_invitation.get(invitation.id)
        
        if feedback and feedback.calculated_score is not None and feedback.max_score is not None:
            # Use stored score from review_feedback
            total_score = float(feedback.calculated_score)
            stored_max_score = float(feedback.max_score)
            percentage = (total_score / stored_max_score * 100) if stored_max_score > 0 else 0.0
            
            score_data = schemas.InvitationScoreData(
                total_score=round(total_score, 2),
                max_score=round(stored_max_score, 2),
                percentage=round(percentage, 2),
            )
        else:
            # Fallback: calculate from ReviewFeatureScore if no stored score
            # Get scores for this invitation
            scores_result = await session.execute(
                select(models.ReviewFeatureScore).where(
                    models.ReviewFeatureScore.invitation_id == invitation.id
                )
            )
            invitation_scores_list = scores_result.scalars().all()
            
            total_score = 0.0
            for feature in features_list:
                # Check if this feature is checked
                for score_entry in invitation_scores_list:
                    if score_entry.feature_id == feature.id and score_entry.checked:
                        total_score += float(feature.weight)
                        break
            
            # Use max_score from features (not from stored feedback)
            percentage = (total_score / max_score * 100) if max_score > 0 else 0.0
            score_data = schemas.InvitationScoreData(
                total_score=round(total_score, 2),
                max_score=round(max_score, 2),
                percentage=round(percentage, 2),
            )

        invitation_scores.append(
            schemas.InvitationScoreSummary(
                invitation_id=invitation.id,
                score=score_data,
            )
        )

    return invitation_scores


@router.put("/{assessment_id}/manual-ranking", response_model=schemas.ManualRankingRead)
async def save_manual_ranking(
    assessment_id: str,
    payload: schemas.ManualRankingUpdate,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> schemas.ManualRankingRead:
    """Save manual ranking order for an assessment."""
    try:
        assessment_uuid = uuid.UUID(assessment_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid assessment id") from exc

    result = await session.execute(
        select(models.Assessment).where(models.Assessment.id == assessment_uuid)
    )
    assessment = result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    await require_org_membership_role(
        session,
        assessment.org_id,
        current_session,
        allowed_roles=("owner", "admin"),
    )

    # Verify all invitation IDs belong to this assessment
    invitation_ids_set = set(payload.invitation_ids)
    result = await session.execute(
        select(models.Invitation)
        .where(
            models.Invitation.id.in_(payload.invitation_ids),
            models.Invitation.assessment_id == assessment_uuid,
        )
    )
    found_invitations = result.scalars().all()
    found_ids = {inv.id for inv in found_invitations}

    if len(found_ids) != len(invitation_ids_set):
        missing_ids = invitation_ids_set - found_ids
        raise HTTPException(
            status_code=400,
            detail=f"Some invitation IDs do not belong to this assessment: {missing_ids}",
        )

    # Delete existing rankings for this assessment
    await session.execute(
        delete(models.AssessmentManualRanking).where(
            models.AssessmentManualRanking.assessment_id == assessment_uuid
        )
    )

    # Create new rankings
    created_by = current_session.user.id if current_session.user else None
    rankings = []
    for order, invitation_id in enumerate(payload.invitation_ids, start=1):
        ranking = models.AssessmentManualRanking(
            assessment_id=assessment_uuid,
            invitation_id=invitation_id,
            display_order=order,
            created_by=created_by,
        )
        session.add(ranking)
        rankings.append(ranking)

    await session.commit()

    # Refresh to get timestamps
    for ranking in rankings:
        await session.refresh(ranking)

    # Get the earliest created_at and latest updated_at
    created_at = min(r.created_at for r in rankings) if rankings else datetime.now()
    updated_at = max(r.updated_at for r in rankings) if rankings else datetime.now()

    return schemas.ManualRankingRead(
        assessment_id=assessment_uuid,
        invitation_ids=payload.invitation_ids,
        created_at=created_at,
        updated_at=updated_at,
    )


@router.get("/{assessment_id}/manual-ranking", response_model=Optional[schemas.ManualRankingRead])
async def get_manual_ranking(
    assessment_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(
        require_roles("authenticated", "service_role", "owner", "admin", "viewer")
    ),
) -> Optional[schemas.ManualRankingRead]:
    """Get manual ranking order for an assessment if it exists."""
    try:
        assessment_uuid = uuid.UUID(assessment_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid assessment id") from exc

    result = await session.execute(
        select(models.Assessment).where(models.Assessment.id == assessment_uuid)
    )
    assessment = result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    await require_org_membership_role(
        session,
        assessment.org_id,
        current_session,
        allowed_roles=("owner", "admin", "viewer"),
    )

    # Get all rankings for this assessment, ordered by display_order
    result = await session.execute(
        select(models.AssessmentManualRanking)
        .where(models.AssessmentManualRanking.assessment_id == assessment_uuid)
        .order_by(models.AssessmentManualRanking.display_order)
    )
    rankings = result.scalars().all()

    if not rankings:
        return None

    invitation_ids = [ranking.invitation_id for ranking in rankings]
    created_at = min(ranking.created_at for ranking in rankings)
    updated_at = max(ranking.updated_at for ranking in rankings)

    return schemas.ManualRankingRead(
        assessment_id=assessment_uuid,
        invitation_ids=invitation_ids,
        created_at=created_at,
        updated_at=updated_at,
    )


@router.delete("/{assessment_id}/manual-ranking", status_code=204)
async def clear_manual_ranking(
    assessment_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> None:
    """Clear manual ranking for an assessment (restore to auto-sort)."""
    try:
        assessment_uuid = uuid.UUID(assessment_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid assessment id") from exc

    result = await session.execute(
        select(models.Assessment).where(models.Assessment.id == assessment_uuid)
    )
    assessment = result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    await require_org_membership_role(
        session,
        assessment.org_id,
        current_session,
        allowed_roles=("owner", "admin"),
    )

    await session.execute(
        delete(models.AssessmentManualRanking).where(
            models.AssessmentManualRanking.assessment_id == assessment_uuid
        )
    )
    await session.commit()

