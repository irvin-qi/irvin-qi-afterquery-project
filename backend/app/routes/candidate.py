"""Candidate-facing endpoints for start and submit flows."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import models, schemas
from ..database import get_session
from ..github_app import GitHubAppError
from ..services.email import (
    EmailServiceError,
    ResendEmailService,
    get_resend_email_service,
)
from ..services.github_installations import require_github_installation_client
from ..utils import hash_token

router = APIRouter(prefix="/api", tags=["candidate"])


logger = logging.getLogger(__name__)


async def _get_invitation_by_token(
    session: AsyncSession, token: str
) -> models.Invitation:
    hashed = hash_token(token)
    result = await session.execute(
        select(models.Invitation)
        .options(
            selectinload(models.Invitation.assessment).selectinload(models.Assessment.seed),
            selectinload(models.Invitation.candidate_repo),
            selectinload(models.Invitation.access_tokens),
        )
        .where(models.Invitation.start_link_token_hash == hashed)
    )
    invitation = result.scalar_one_or_none()
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    return invitation


def _duration_hours(value: timedelta | None) -> int:
    if value is None:
        return 0
    return int(value.total_seconds() // 3600)


@router.get("/start/{token}", response_model=schemas.CandidateStartData)
async def get_invitation_details(
    token: str, session: AsyncSession = Depends(get_session)
) -> schemas.CandidateStartData:
    invitation = await _get_invitation_by_token(session, token)
    assessment = invitation.assessment
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    seed = assessment.seed
    if seed is None:
        raise HTTPException(status_code=404, detail="Assessment seed not found")

    candidate_repo = invitation.candidate_repo

    return schemas.CandidateStartData(
        invitation=schemas.CandidateInvitation(
            id=str(invitation.id),
            assessment_id=str(invitation.assessment_id),
            candidate_email=invitation.candidate_email,
            candidate_name=invitation.candidate_name,
            status=invitation.status.value,
            start_deadline=invitation.start_deadline,
            complete_deadline=invitation.complete_deadline,
            sent_at=invitation.sent_at,
            started_at=invitation.started_at,
            submitted_at=invitation.submitted_at,
        ),
        assessment=schemas.CandidateAssessment(
            id=str(assessment.id),
            seed_id=str(assessment.seed_id),
            title=assessment.title,
            description=assessment.description,
            instructions=assessment.instructions,
            candidate_email_subject=assessment.candidate_email_subject,
            candidate_email_body=assessment.candidate_email_body,
            time_to_start_hours=_duration_hours(assessment.time_to_start),
            time_to_complete_hours=_duration_hours(assessment.time_to_complete),
        ),
        seed=schemas.CandidateSeed(
            id=str(seed.id),
            seed_repo=seed.seed_repo_full_name,
            seed_repo_url=f"https://github.com/{seed.seed_repo_full_name}",
            latest_main_sha=seed.latest_main_sha,
            source_repo_url=seed.source_repo_url,
        ),
        candidate_repo=(
            schemas.CandidateRepoInfo(
                id=str(candidate_repo.id),
                invitation_id=str(candidate_repo.invitation_id),
                repo_full_name=candidate_repo.repo_full_name,
                repo_html_url=candidate_repo.repo_html_url,
                seed_sha_pinned=candidate_repo.seed_sha_pinned,
                started_at=candidate_repo.created_at,
                last_commit_at=None,
            )
            if candidate_repo is not None
            else None
        ),
    )


@router.post("/start/{token}", response_model=schemas.StartAssessmentResponse)
async def start_assessment(
    token: str,
    session: AsyncSession = Depends(get_session),
    email_service: ResendEmailService = Depends(get_resend_email_service),
) -> schemas.StartAssessmentResponse:
    invitation = await _get_invitation_by_token(session, token)

    now = datetime.now(timezone.utc)
    if invitation.start_deadline and now > invitation.start_deadline:
        invitation.status = models.InvitationStatus.expired
        invitation.expired_at = now
        await session.commit()
        raise HTTPException(status_code=410, detail="Invitation start window has expired")

    if invitation.status in (models.InvitationStatus.started, models.InvitationStatus.submitted):
        raise HTTPException(status_code=409, detail="Assessment already started")

    assessment = invitation.assessment
    if assessment is None or assessment.seed is None:
        raise HTTPException(status_code=400, detail="Assessment seed configuration missing")

    if not assessment.seed.latest_main_sha:
        raise HTTPException(status_code=400, detail="Seed repository does not have a pinned main SHA")

    invitation.status = models.InvitationStatus.started
    invitation.started_at = now
    invitation.complete_deadline = now + assessment.time_to_complete

    seed_model = assessment.seed

    github = await require_github_installation_client(session, seed_model.org_id)

    default_branch = seed_model.default_branch or "main"

    try:
        latest_seed_sha = await github.refresh_branch_sha(
            seed_model.seed_repo_full_name, branch=default_branch
        )
    except GitHubAppError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if latest_seed_sha != seed_model.latest_main_sha:
        seed_model.latest_main_sha = latest_seed_sha

    if invitation.candidate_repo is None:
        candidate_slug = invitation.id.hex[:10]
        try:
            repo_info = await github.create_candidate_repository(
                seed_model.seed_repo_full_name,
                default_branch=default_branch,
                candidate_slug=candidate_slug,
            )
        except GitHubAppError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        candidate_repo = models.CandidateRepo(
            invitation_id=invitation.id,
            seed_sha_pinned=latest_seed_sha,
            repo_full_name=repo_info.full_name,
            repo_html_url=repo_info.html_url,
            github_repo_id=repo_info.id,
        )
        session.add(candidate_repo)
        await session.flush()
        await session.refresh(candidate_repo)
    else:
        candidate_repo = invitation.candidate_repo
        latest_seed_sha = candidate_repo.seed_sha_pinned

    for token_model in invitation.access_tokens:
        if not token_model.revoked:
            token_model.revoked = True

    if candidate_repo.github_repo_id is None:
        raise HTTPException(
            status_code=500,
            detail="Candidate repository is missing GitHub metadata",
        )

    try:
        github_token, github_expires_at = await github.create_repository_access_token(
            candidate_repo.github_repo_id
        )
    except GitHubAppError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    access_token_value = github_token
    access_token = models.AccessToken(
        invitation_id=invitation.id,
        repo_full_name=candidate_repo.repo_full_name,
        opaque_token_hash=hash_token(access_token_value),
        expires_at=github_expires_at,
    )
    session.add(access_token)
    await session.commit()
    await session.refresh(candidate_repo)
    await session.refresh(access_token)

    try:
        sent_notification = await email_service.send_candidate_status_email(
            session,
            invitation=invitation,
            assessment=assessment,
            event_type=models.EmailEventType.assessment_started,
            extra_context={
                "candidate_repo_url": candidate_repo.repo_html_url or "",
                "candidate_repo_name": candidate_repo.repo_full_name,
            },
        )
    except EmailServiceError as exc:
        logger.warning("Resend failed to send assessment started email: %s", exc)
    else:
        if sent_notification:
            await session.commit()

    return schemas.StartAssessmentResponse(
        invitation_id=str(invitation.id),
        status=invitation.status.value,
        started_at=invitation.started_at,
        complete_deadline=invitation.complete_deadline,
        candidate_repo=schemas.CandidateRepoRead.from_orm(candidate_repo),
        access_token=access_token_value,
        access_token_expires_at=access_token.expires_at,
    )


@router.post("/submit/{token}", response_model=schemas.SubmitResponse)
async def submit_assessment(
    token: str,
    payload: schemas.SubmitRequest,
    session: AsyncSession = Depends(get_session),
    email_service: ResendEmailService = Depends(get_resend_email_service),
) -> schemas.SubmitResponse:
    invitation = await _get_invitation_by_token(session, token)

    assessment = invitation.assessment
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    if invitation.status != models.InvitationStatus.started:
        raise HTTPException(status_code=409, detail="Assessment is not in a started state")

    candidate_repo = invitation.candidate_repo
    if candidate_repo is None:
        raise HTTPException(status_code=400, detail="Candidate repository has not been provisioned")

    seed_model = assessment.seed
    if seed_model is None:
        raise HTTPException(status_code=404, detail="Assessment seed not found")

    now = datetime.now(timezone.utc)
    invitation.status = models.InvitationStatus.submitted
    invitation.submitted_at = now

    final_sha = payload.final_sha or candidate_repo.seed_sha_pinned

    submission = models.Submission(
        invitation_id=invitation.id,
        final_sha=final_sha,
        repo_html_url=payload.repo_html_url or candidate_repo.repo_html_url,
        video_url=payload.video_url,
    )
    session.add(submission)

    # Revoke all active access tokens for this invitation
    for token_model in invitation.access_tokens:
        if not token_model.revoked:
            token_model.revoked = True

    github = await require_github_installation_client(session, seed_model.org_id)

    try:
        await github.archive_repository(candidate_repo.repo_full_name)
        candidate_repo.archived = True
        candidate_repo.active = False
    except GitHubAppError:
        candidate_repo.active = False

    await session.commit()
    await session.refresh(submission)

    try:
        sent_notification = await email_service.send_candidate_status_email(
            session,
            invitation=invitation,
            assessment=assessment,
            event_type=models.EmailEventType.submission_received,
            extra_context={
                "candidate_repo_url": candidate_repo.repo_html_url if candidate_repo else "",
                "candidate_repo_name": candidate_repo.repo_full_name if candidate_repo else "",
            },
        )
    except EmailServiceError as exc:
        logger.warning("Resend failed to send submission received email: %s", exc)
    else:
        if sent_notification:
            await session.commit()

    return schemas.SubmitResponse(
        invitation_id=str(invitation.id),
        submission_id=str(submission.id),
        final_sha=submission.final_sha,
        submitted_at=invitation.submitted_at,
        status=invitation.status.value,
        video_url=submission.video_url,
    )

