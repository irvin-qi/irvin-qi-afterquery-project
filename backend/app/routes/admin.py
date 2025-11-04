"""Administrative endpoints for bootstrapping the database."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import migrations, models, schemas, utils
from ..services.github_installations import github_installation_to_schema
from ..services.email import (
    CANDIDATE_ASSESSMENT_STARTED_TEMPLATE_KEY,
    CANDIDATE_ASSESSMENT_SUBMITTED_TEMPLATE_KEY,
)
from ..auth import SupabaseSession, require_roles
from ..database import ASYNC_ENGINE, get_session

router = APIRouter(prefix="/api/admin", tags=["admin"])


_EMAIL_TEMPLATE_METADATA: dict[str, dict[str, str]] = {
    CANDIDATE_ASSESSMENT_STARTED_TEMPLATE_KEY: {
        "name": "Assessment in progress",
        "description": "Sent to candidates when they begin an assessment.",
    },
    CANDIDATE_ASSESSMENT_SUBMITTED_TEMPLATE_KEY: {
        "name": "Submission received",
        "description": "Sent to candidates after they submit their work.",
    },
}

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEMO_DATA_PATH = _REPO_ROOT / "db" / "demo_seed_data.json"


def _email_template_to_schema(template: models.EmailTemplate) -> schemas.AdminEmailTemplate:
    metadata = _EMAIL_TEMPLATE_METADATA.get(template.key or "")
    name = metadata.get("name") if metadata else (template.key or (template.subject or "Template"))
    description = metadata.get("description") if metadata else ""
    return schemas.AdminEmailTemplate(
        id=str(template.id),
        org_id=str(template.org_id),
        key=template.key,
        name=name,
        subject=template.subject,
        body=template.body,
        description=description,
        updated_at=template.created_at,
    )


async def _resolve_org_for_email_templates(
    session: AsyncSession, current_session: SupabaseSession
) -> tuple[models.Org, Optional[models.OrgMember]]:
    membership_result = await session.execute(
        select(models.OrgMember)
        .where(models.OrgMember.supabase_user_id == current_session.user.id)
        .order_by(models.OrgMember.created_at)
    )
    membership = membership_result.scalars().first()

    if membership is None:
        if current_session.user.has_role("service_role"):
            org = await _fetch_org(session)
            return org, None
        raise HTTPException(status_code=403, detail="Organization membership required")

    org = await _fetch_org(session, membership.org_id)
    return org, membership

def _normalize_email(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _find_membership_for_email(
    org: models.Org, email: Optional[str]
) -> Optional[models.OrgMember]:
    normalized_email = _normalize_email(email)
    if not normalized_email:
        return None
    for membership in org.members:
        if membership.email:
            member_email = _normalize_email(membership.email)
            if member_email == normalized_email:
                return membership
    return None


def _derive_supabase_display_name(session: Optional[SupabaseSession]) -> Optional[str]:
    if session is None:
        return None
    metadata = session.user.user_metadata if session.user.user_metadata else {}
    if isinstance(metadata, dict):
        for key in ("full_name", "name"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if session.user.email:
        return session.user.email
    return None


def _membership_to_schema(
    membership: Optional[models.OrgMember],
) -> Optional[schemas.AdminMembership]:
    if membership is None:
        return None
    return schemas.AdminMembership(
        org_id=str(membership.org_id),
        supabase_user_id=str(membership.supabase_user_id),
        role=membership.role,
        is_approved=membership.is_approved,
    )


def _build_admin_user(
    membership: Optional[models.OrgMember],
    supabase_session: Optional[SupabaseSession],
) -> Optional[schemas.AdminUser]:
    if membership is not None:
        name = (
            membership.display_name
            or membership.email
            or str(membership.supabase_user_id)
        )
        return schemas.AdminUser(
            id=str(membership.supabase_user_id),
            email=membership.email,
            name=name,
            role=membership.role,
        )

    if supabase_session is not None:
        derived_name = _derive_supabase_display_name(supabase_session)
        return schemas.AdminUser(
            id=str(supabase_session.user.id),
            email=supabase_session.user.email,
            name=derived_name,
            role=supabase_session.user.role,
        )

    return None


async def _apply_schema() -> int:
    """Execute the schema SQL file against the connected database."""

    try:
        _, bytes_applied = await migrations.ensure_schema(ASYNC_ENGINE)
    except RuntimeError as exc:  # pragma: no cover - developer misconfiguration
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return bytes_applied


def _load_demo_data() -> dict:
    """Load demo seed configuration from the repository JSON file."""

    try:
        payload = _DEMO_DATA_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:  # pragma: no cover - developer misconfiguration
        raise HTTPException(status_code=500, detail="Demo data file not found") from exc

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:  # pragma: no cover - developer misconfiguration
        raise HTTPException(status_code=500, detail="Demo data file is invalid JSON") from exc

    return data


async def _seed_demo_data(session: AsyncSession) -> schemas.SeedSummary:
    """Seed a minimal organization, membership, and assessment if absent."""

    demo_data = _load_demo_data()

    org_config = demo_data.get("org", {})
    seed_config = demo_data.get("seed", {})
    assessment_config = demo_data.get("assessment", {})
    invitation_config = demo_data.get("invitation", {})

    demo_org_name = org_config.get("name", "Demo Assessment Org")
    members = org_config.get("members", [])
    owner_config = next((member for member in members if member.get("role") == "owner"), None)
    if owner_config is None and members:
        owner_config = members[0]

    demo_user_email = (owner_config or {}).get("email", "founder@example.com")
    demo_user_name = (owner_config or {}).get("name", "Demo Founder")
    owner_supabase_id_raw = (owner_config or {}).get("supabase_user_id")
    owner_is_approved = bool((owner_config or {}).get("is_approved", True))

    owner_supabase_id: uuid.UUID
    if owner_supabase_id_raw:
        try:
            owner_supabase_id = uuid.UUID(owner_supabase_id_raw)
        except ValueError:
            owner_supabase_id = uuid.uuid5(uuid.NAMESPACE_DNS, owner_supabase_id_raw)
    else:
        # Generate a stable UUID based on the email for demo purposes.
        seed_value = demo_user_email or "demo-owner@example.com"
        owner_supabase_id = uuid.uuid5(uuid.NAMESPACE_DNS, seed_value)

    demo_seed_repo = seed_config.get("seed_repo_full_name", "example/fullstack-seed")
    demo_source_repo = seed_config.get("source_repo_url", "https://github.com/example/fullstack-seed")
    demo_default_branch = seed_config.get("default_branch", "main")
    demo_is_template = seed_config.get("is_template", True)
    demo_latest_main_sha = seed_config.get("latest_main_sha")

    demo_assessment_title = assessment_config.get("title", "Full Stack Product Challenge")
    demo_assessment_description = assessment_config.get(
        "description", "Build an end-to-end feature using the provided template."
    )
    demo_instructions = assessment_config.get(
        "instructions", "Follow the README in the generated repository to get started."
    )
    demo_candidate_email_subject = assessment_config.get(
        "candidate_email_subject", "Your interview project is ready"
    )
    demo_candidate_email_body = assessment_config.get(
        "candidate_email_body", "Welcome! Clone the repo and submit within 48 hours."
    )
    demo_time_to_start = timedelta(hours=assessment_config.get("time_to_start_hours", 72))
    demo_time_to_complete = timedelta(hours=assessment_config.get("time_to_complete_hours", 48))

    demo_candidate_email = invitation_config.get("candidate_email", "candidate@example.com")
    demo_candidate_name = invitation_config.get("candidate_name", "Demo Candidate")

    created_org = False
    created_membership = False
    created_seed = False
    created_assessment = False
    created_invitation = False
    invitation_start_token: Optional[str] = None

    org_result = await session.execute(select(models.Org).where(models.Org.name == demo_org_name))
    org = org_result.scalar_one_or_none()
    if org is None:
        org = models.Org(name=demo_org_name)
        session.add(org)
        await session.flush()
        created_org = True

    membership_result = await session.execute(
        select(models.OrgMember).where(
            models.OrgMember.org_id == org.id,
            models.OrgMember.supabase_user_id == owner_supabase_id,
        )
    )
    membership = membership_result.scalar_one_or_none()
    if membership is None:
        membership = models.OrgMember(
            org_id=org.id,
            supabase_user_id=owner_supabase_id,
            email=demo_user_email,
            display_name=demo_user_name,
            role="owner",
            is_approved=owner_is_approved,
        )
        session.add(membership)
        created_membership = True
    else:
        updated = False
        if membership.role != "owner":
            membership.role = "owner"
            updated = True
        if membership.email != demo_user_email:
            membership.email = demo_user_email
            updated = True
        if membership.display_name != demo_user_name:
            membership.display_name = demo_user_name
            updated = True
        if membership.is_approved != owner_is_approved:
            membership.is_approved = owner_is_approved
            updated = True
        if updated:
            session.add(membership)

    seed_result = await session.execute(
        select(models.Seed).where(
            models.Seed.org_id == org.id,
            models.Seed.seed_repo_full_name == demo_seed_repo,
        )
    )
    seed = seed_result.scalar_one_or_none()
    if seed is None:
        seed = models.Seed(
            org_id=org.id,
            source_repo_url=demo_source_repo,
            seed_repo_full_name=demo_seed_repo,
            default_branch=demo_default_branch,
            is_template=demo_is_template,
            latest_main_sha=demo_latest_main_sha,
        )
        session.add(seed)
        await session.flush()
        created_seed = True

    assessment_result = await session.execute(
        select(models.Assessment).where(
            models.Assessment.org_id == org.id,
            models.Assessment.title == demo_assessment_title,
        )
    )
    assessment = assessment_result.scalar_one_or_none()
    if assessment is None:
        assessment = models.Assessment(
            org_id=org.id,
            seed_id=seed.id,
            title=demo_assessment_title,
            description=demo_assessment_description,
            instructions=demo_instructions,
            candidate_email_subject=demo_candidate_email_subject,
            candidate_email_body=demo_candidate_email_body,
            time_to_start=demo_time_to_start,
            time_to_complete=demo_time_to_complete,
            created_by=owner_supabase_id,
        )
        session.add(assessment)
        await session.flush()
        created_assessment = True

    invitation_result = await session.execute(
        select(models.Invitation).where(
            models.Invitation.assessment_id == assessment.id,
            models.Invitation.candidate_email == demo_candidate_email,
        )
    )
    invitation = invitation_result.scalar_one_or_none()
    if invitation is None:
        raw_token = utils.generate_token()
        now = datetime.now(timezone.utc)
        start_deadline = now + demo_time_to_start
        complete_deadline = start_deadline + demo_time_to_complete
        invitation = models.Invitation(
            assessment_id=assessment.id,
            candidate_email=demo_candidate_email,
            candidate_name=demo_candidate_name,
            start_link_token_hash=utils.hash_token(raw_token),
            start_deadline=start_deadline,
            complete_deadline=complete_deadline,
        )
        session.add(invitation)
        await session.flush()
        invitation_start_token = raw_token
        created_invitation = True

    await session.commit()

    return schemas.SeedSummary(
        created_org=created_org,
        org_id=str(org.id),
        created_owner_membership=created_membership,
        owner_supabase_user_id=str(owner_supabase_id),
        owner_email=demo_user_email,
        owner_is_approved=owner_is_approved,
        created_seed=created_seed,
        seed_id=str(seed.id),
        created_assessment=created_assessment,
        assessment_id=str(assessment.id),
        created_invitation=created_invitation,
        invitation_id=str(invitation.id),
        invitation_start_token=invitation_start_token,
    )


@router.post("/bootstrap", response_model=schemas.BootstrapResponse)
async def bootstrap_database(
    session: AsyncSession = Depends(get_session),
) -> schemas.BootstrapResponse:
    """Apply database schema migrations and seed initial demo data."""

    applied_bytes = await _apply_schema()
    seed_summary = await _seed_demo_data(session)

    return schemas.BootstrapResponse(
        migrated=applied_bytes > 0,
        schema_path=str(migrations.SCHEMA_PATH),
        seed=seed_summary,
    )


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "org"


def _duration_hours(value: Optional[timedelta]) -> int:
    if value is None:
        return 0
    return int(value.total_seconds() // 3600)


async def _fetch_org(
    session: AsyncSession, org_id: Optional[uuid.UUID] = None
) -> models.Org:
    query = (
        select(models.Org)
        .options(
            selectinload(models.Org.members),
            selectinload(models.Org.seeds),
            selectinload(models.Org.github_installation),
        )
        .order_by(models.Org.created_at)
    )

    if org_id is not None:
        query = query.where(models.Org.id == org_id)
    else:
        query = query.limit(1)

    result = await session.execute(query)
    org = result.scalar_one_or_none()
    if org is None:
        detail = "Organization not found" if org_id is not None else "No organizations available"
        raise HTTPException(status_code=404, detail=detail)
    return org


async def _build_admin_overview(
    session: AsyncSession,
    org: models.Org,
    membership: Optional[models.OrgMember],
    supabase_session: Optional[SupabaseSession] = None,
) -> schemas.AdminOrgOverview:
    assessments_result = await session.execute(
        select(models.Assessment)
        .options(
            selectinload(models.Assessment.invitations).selectinload(
                models.Invitation.candidate_repo
            ),
            selectinload(models.Assessment.seed),
        )
        .where(models.Assessment.org_id == org.id)
        .order_by(models.Assessment.created_at.desc())
    )
    assessments = assessments_result.scalars().all()

    invitations: list[models.Invitation] = []
    candidate_repos: list[models.CandidateRepo] = []
    for assessment in assessments:
        sorted_invites = sorted(
            assessment.invitations, key=lambda invite: invite.sent_at, reverse=True
        )
        invitations.extend(sorted_invites)
        for invite in sorted_invites:
            if invite.candidate_repo is not None:
                candidate_repos.append(invite.candidate_repo)

    invitation_ids = [invite.id for invite in invitations]
    if invitation_ids:
        review_comments_result = await session.execute(
            select(models.ReviewComment)
            .where(models.ReviewComment.invitation_id.in_(invitation_ids))
            .order_by(models.ReviewComment.created_at.desc())
        )
        review_comments = review_comments_result.scalars().all()

        submissions_result = await session.execute(
            select(models.Submission)
            .where(models.Submission.invitation_id.in_(invitation_ids))
            .order_by(models.Submission.created_at.desc())
        )
        submissions = submissions_result.scalars().all()
        submission_map: dict[uuid.UUID, models.Submission] = {}
        for submission in submissions:
            if submission.invitation_id not in submission_map:
                submission_map[submission.invitation_id] = submission
    else:
        review_comments = []
        submission_map = {}

    membership_map = {
        member.supabase_user_id: member for member in org.members
    }

    templates_result = await session.execute(
        select(models.EmailTemplate)
        .where(models.EmailTemplate.org_id == org.id)
        .order_by(models.EmailTemplate.created_at.desc())
    )
    templates = templates_result.scalars().all()

    seeds = sorted(org.seeds, key=lambda seed: seed.created_at, reverse=True)

    current_admin = _build_admin_user(membership, supabase_session)
    membership_schema = _membership_to_schema(membership)

    return schemas.AdminOrgOverview(
        org=schemas.AdminOrg(id=str(org.id), name=org.name, slug=_slugify(org.name)),
        current_admin=current_admin,
        membership=membership_schema,
        seeds=[
            schemas.AdminSeed(
                id=str(seed.id),
                source_repo_url=seed.source_repo_url,
                seed_repo=seed.seed_repo_full_name,
                seed_repo_url=f"https://github.com/{seed.seed_repo_full_name}",
                default_branch=seed.default_branch,
                latest_main_sha=seed.latest_main_sha,
                created_at=seed.created_at,
            )
            for seed in seeds
        ],
        assessments=[
            schemas.AdminAssessment(
                id=str(assessment.id),
                org_id=str(assessment.org_id),
                seed_id=str(assessment.seed_id),
                title=assessment.title,
                description=assessment.description,
                instructions=assessment.instructions,
                candidate_email_subject=assessment.candidate_email_subject,
                candidate_email_body=assessment.candidate_email_body,
                time_to_start_hours=_duration_hours(assessment.time_to_start),
                time_to_complete_hours=_duration_hours(assessment.time_to_complete),
                created_by=str(assessment.created_by)
                if assessment.created_by is not None
                else None,
                created_at=assessment.created_at,
                rubric_text=assessment.rubric_text,
                sort_mode=assessment.sort_mode or "auto",
            )
            for assessment in assessments
        ],
        invitations=[
            schemas.AdminInvitation(
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
                video_url=submission_map[invitation.id].video_url if invitation.id in submission_map else None,
            )
            for invitation in invitations
        ],
        candidate_repos=[
            schemas.AdminCandidateRepo(
                id=str(repo.id),
                invitation_id=str(repo.invitation_id),
                seed_sha_pinned=repo.seed_sha_pinned,
                repo_full_name=repo.repo_full_name,
                repo_html_url=repo.repo_html_url,
                started_at=repo.created_at,
                last_commit_at=None,
            )
            for repo in sorted(candidate_repos, key=lambda repo: repo.created_at, reverse=True)
        ],
        review_comments=[
            schemas.AdminReviewComment(
                id=str(comment.id),
                invitation_id=str(comment.invitation_id),
                author=(
                    membership_map[comment.created_by].display_name
                    if comment.created_by in membership_map
                    and membership_map[comment.created_by].display_name
                    else (
                        membership_map[comment.created_by].email
                        if comment.created_by in membership_map
                        else None
                    )
                ),
                body=comment.body,
                created_at=comment.created_at,
            )
            for comment in review_comments
        ],
        email_templates=[
            _email_template_to_schema(template)
            for template in templates
        ],
        github_installation=github_installation_to_schema(org.github_installation),
    )


def _empty_admin_overview(
    org: Optional[models.Org],
    membership: Optional[models.OrgMember],
    supabase_session: Optional[SupabaseSession],
) -> schemas.AdminOrgOverview:
    org_schema = (
        schemas.AdminOrg(id=str(org.id), name=org.name, slug=_slugify(org.name))
        if org is not None
        else None
    )

    return schemas.AdminOrgOverview(
        org=org_schema,
        current_admin=_build_admin_user(membership, supabase_session),
        membership=_membership_to_schema(membership),
        seeds=[],
        assessments=[],
        invitations=[],
        candidate_repos=[],
        review_comments=[],
        email_templates=[],
        github_installation=github_installation_to_schema(
            org.github_installation if org is not None else None
        ),
    )


@router.put("/email-templates/{template_key}", response_model=schemas.AdminEmailTemplate)
async def upsert_email_template(
    template_key: str,
    payload: schemas.EmailTemplateUpsert,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(
        require_roles("authenticated", "admin", "service_role")
    ),
) -> schemas.AdminEmailTemplate:
    normalized_key = template_key.strip().lower()
    metadata = _EMAIL_TEMPLATE_METADATA.get(normalized_key)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Email template not recognized")

    org, membership = await _resolve_org_for_email_templates(session, current_session)

    if not current_session.user.has_role("service_role"):
        if membership is None or membership.role not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="Administrator privileges required")
        if not membership.is_approved:
            raise HTTPException(status_code=403, detail="Organization membership requires approval")

    subject = (payload.subject or "").strip()
    body = (payload.body or "").strip()
    if not subject or not body:
        raise HTTPException(status_code=400, detail="Subject and body are required")

    result = await session.execute(
        select(models.EmailTemplate)
        .where(models.EmailTemplate.org_id == org.id)
        .where(models.EmailTemplate.key == normalized_key)
    )
    template = result.scalar_one_or_none()

    if template is None:
        template = models.EmailTemplate(
            org_id=org.id,
            key=normalized_key,
            subject=subject,
            body=body,
        )
        session.add(template)
    else:
        template.subject = subject
        template.body = body

    await session.commit()
    await session.refresh(template)

    return _email_template_to_schema(template)


@router.get("/overview", response_model=schemas.AdminOrgOverview)
async def get_admin_overview(
    org_id: Optional[str] = Query(default=None, alias="orgId"),
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(
        require_roles("authenticated", "admin", "service_role")
    ),
) -> schemas.AdminOrgOverview:
    """Return an overview of the organization visible to the current admin."""

    requested_org_id: Optional[uuid.UUID] = None
    if org_id:
        try:
            requested_org_id = uuid.UUID(org_id)
        except ValueError as exc:  # pragma: no cover - invalid client input
            raise HTTPException(status_code=400, detail="Invalid organization id") from exc

    membership_query = (
        select(models.OrgMember)
        .where(models.OrgMember.supabase_user_id == current_session.user.id)
        .order_by(models.OrgMember.created_at)
    )
    if requested_org_id is not None:
        membership_query = membership_query.where(
            models.OrgMember.org_id == requested_org_id
        )

    membership_result = await session.execute(membership_query)
    membership = membership_result.scalars().first()

    target_org_id = requested_org_id or (membership.org_id if membership else None)

    org: Optional[models.Org] = None
    if target_org_id is not None:
        org = await _fetch_org(session, target_org_id)
    elif current_session.user.has_role("service_role"):
        # Service role tokens may request the first available organization.
        org = await _fetch_org(session)

    if membership is None and org is not None:
        membership = _find_membership_for_email(org, current_session.user.email)

    is_service_role = current_session.user.has_role("service_role")

    if membership is None and not is_service_role:
        return _empty_admin_overview(None, None, current_session)

    if (
        membership is not None
        and not membership.is_approved
        and not is_service_role
    ):
        return _empty_admin_overview(org, membership, current_session)

    if org is None:
        return _empty_admin_overview(None, membership, current_session)

    return await _build_admin_overview(session, org, membership, current_session)
