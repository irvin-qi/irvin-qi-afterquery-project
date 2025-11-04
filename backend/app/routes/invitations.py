"""Invitation management endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import models, schemas
from ..auth import SupabaseSession, require_roles
from ..database import get_session
from ..utils import generate_token, hash_token
from ..services.email import (
    EmailServiceError,
    InvitationEmailPayload,
    ResendEmailService,
    get_resend_email_service,
)
from ..services.supabase_memberships import require_org_membership_role

router = APIRouter(prefix="/api/invitations", tags=["invitations"])


async def _load_assessment(
    session: AsyncSession, assessment_id: uuid.UUID
) -> models.Assessment:
    result = await session.execute(
        select(models.Assessment)
        .options(selectinload(models.Assessment.seed))
        .where(models.Assessment.id == assessment_id)
    )
    assessment = result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return assessment


@router.post("", response_model=list[schemas.InvitationRead], status_code=201)
async def create_invitations(
    payload: schemas.InvitationBatchCreate,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
    email_service: ResendEmailService = Depends(get_resend_email_service),
) -> list[schemas.InvitationRead]:
    assessment_id = payload.assessment_id

    assessment = await _load_assessment(session, assessment_id)

    await require_org_membership_role(
        session,
        assessment.org_id,
        current_session,
        allowed_roles=("owner", "admin"),
    )

    now = datetime.now(timezone.utc)
    start_deadline = now + assessment.time_to_start

    created_invitations: list[schemas.InvitationRead] = []
    for invite_payload in payload.invitations:
        raw_token = generate_token()
        invitation = models.Invitation(
            assessment_id=assessment_id,
            candidate_email=invite_payload.candidate_email,
            candidate_name=invite_payload.candidate_name,
            status=models.InvitationStatus.sent,
            start_deadline=start_deadline,
            start_link_token_hash=hash_token(raw_token),
        )
        session.add(invitation)
        await session.flush()
        await session.refresh(invitation)
        try:
            await email_service.send_invitation_email(
                session,
                InvitationEmailPayload(
                    invitation=invitation,
                    assessment=assessment,
                    start_link_token=raw_token,
                ),
            )
        except EmailServiceError as exc:
            await session.rollback()
            raise HTTPException(status_code=502, detail="Failed to send invitation email") from exc

        created_invitations.append(
            schemas.InvitationRead(
                id=str(invitation.id),
                assessment_id=str(assessment_id),
                candidate_email=invitation.candidate_email,
                candidate_name=invitation.candidate_name,
                status=invitation.status.value,
                start_deadline=invitation.start_deadline,
                complete_deadline=invitation.complete_deadline,
                start_link_token=raw_token,
                sent_at=invitation.sent_at,
            )
        )
    await session.commit()
    return created_invitations


@router.get("/{invitation_id}", response_model=schemas.InvitationDetail)
async def get_invitation(
    invitation_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(
        require_roles("owner", "admin", "viewer", "service_role")
    ),
) -> schemas.InvitationDetail:
    try:
        invitation_uuid = uuid.UUID(invitation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid invitation id") from exc

    result = await session.execute(select(models.Invitation).where(models.Invitation.id == invitation_uuid))
    invitation = result.scalar_one_or_none()
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    return schemas.InvitationDetail(
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
        expired_at=invitation.expired_at,
    )


@router.post(
    "/{invitation_id}/mark-submitted",
    response_model=schemas.AdminInvitation,
)
async def mark_invitation_submitted(
    invitation_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(
        require_roles("authenticated", "service_role")
    ),
) -> schemas.AdminInvitation:
    try:
        invitation_uuid = uuid.UUID(invitation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid invitation id") from exc

    result = await session.execute(
        select(models.Invitation)
        .options(selectinload(models.Invitation.assessment))
        .where(models.Invitation.id == invitation_uuid)
    )
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
        allowed_roles=("owner", "admin"),
    )

    status_changed = False
    if invitation.status != models.InvitationStatus.submitted:
        invitation.status = models.InvitationStatus.submitted
        invitation.submitted_at = invitation.submitted_at or datetime.now(timezone.utc)
        status_changed = True

    if status_changed:
        await session.commit()

    await session.refresh(invitation)

    return schemas.AdminInvitation(
        id=str(invitation.id),
        assessment_id=str(invitation.assessment_id),
        candidate_email=invitation.candidate_email,
        candidate_name=invitation.candidate_name,
        status=invitation.status.value,
        start_deadline=invitation.start_deadline,
        complete_deadline=invitation.complete_deadline,
        start_link_token=None,
        sent_at=invitation.sent_at,
        started_at=invitation.started_at,
        submitted_at=invitation.submitted_at,
    )


async def _load_invitation_with_assessment(
    session: AsyncSession, invitation_id: uuid.UUID
) -> models.Invitation:
    """Load an invitation with its assessment for authorization checks."""
    result = await session.execute(
        select(models.Invitation)
        .options(selectinload(models.Invitation.assessment))
        .where(models.Invitation.id == invitation_id)
    )
    invitation = result.scalar_one_or_none()
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    return invitation


@router.patch(
    "/{invitation_id}/revoke",
    response_model=schemas.AdminInvitation,
)
async def revoke_invitation(
    invitation_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(
        require_roles("authenticated", "service_role")
    ),
) -> schemas.AdminInvitation:
    """Revoke an invitation by setting its status to revoked."""
    try:
        invitation_uuid = uuid.UUID(invitation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid invitation id") from exc

    invitation = await _load_invitation_with_assessment(session, invitation_uuid)

    assessment = invitation.assessment
    if assessment is None:
        raise HTTPException(status_code=500, detail="Invitation missing assessment")

    await require_org_membership_role(
        session,
        assessment.org_id,
        current_session,
        allowed_roles=("owner", "admin"),
    )

    status_changed = False
    if invitation.status != models.InvitationStatus.revoked:
        invitation.status = models.InvitationStatus.revoked
        invitation.expired_at = invitation.expired_at or datetime.now(timezone.utc)
        status_changed = True

    if status_changed:
        await session.commit()

    await session.refresh(invitation)

    return schemas.AdminInvitation(
        id=str(invitation.id),
        assessment_id=str(invitation.assessment_id),
        candidate_email=invitation.candidate_email,
        candidate_name=invitation.candidate_name,
        status=invitation.status.value,
        start_deadline=invitation.start_deadline,
        complete_deadline=invitation.complete_deadline,
        start_link_token=None,
        sent_at=invitation.sent_at,
        started_at=invitation.started_at,
        submitted_at=invitation.submitted_at,
    )


@router.delete(
    "/{invitation_id}",
    status_code=204,
)
async def delete_invitation(
    invitation_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(
        require_roles("authenticated", "service_role")
    ),
) -> None:
    """Delete an invitation permanently."""
    try:
        invitation_uuid = uuid.UUID(invitation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid invitation id") from exc

    invitation = await _load_invitation_with_assessment(session, invitation_uuid)

    assessment = invitation.assessment
    if assessment is None:
        raise HTTPException(status_code=500, detail="Invitation missing assessment")

    await require_org_membership_role(
        session,
        assessment.org_id,
        current_session,
        allowed_roles=("owner", "admin"),
    )

    await session.delete(invitation)
    await session.commit()

