"""Seed management endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models, schemas
from ..auth import SupabaseSession, require_roles
from ..database import get_session
from ..github_app import GitHubAppError
from ..services.github_installations import require_github_installation_client
from ..services.supabase_memberships import require_org_membership_role

router = APIRouter(prefix="/api/seeds", tags=["seeds"])


@router.post("", response_model=schemas.SeedRead, status_code=201)
async def create_seed(
    payload: schemas.SeedCreate,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> schemas.SeedRead:
    org_id = payload.org_id

    org_result = await session.execute(select(models.Org).where(models.Org.id == org_id))
    if org_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    await require_org_membership_role(
        session,
        org_id,
        current_session,
        allowed_roles=("owner", "admin"),
    )

    github = await require_github_installation_client(session, org_id)

    try:
        repo, latest_sha, canonical_source = await github.ensure_seed_repository(
            payload.source_repo_url, default_branch=payload.default_branch
        )
    except GitHubAppError as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Failed to create seed repository: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    seed = models.Seed(
        org_id=org_id,
        source_repo_url=canonical_source,
        seed_repo_full_name=repo.full_name,
        default_branch=repo.default_branch,
        is_template=True,
        latest_main_sha=latest_sha,
    )
    session.add(seed)
    await session.commit()
    await session.refresh(seed)
    return schemas.SeedRead.from_orm(seed)


@router.get("/{seed_id}", response_model=schemas.SeedRead)
async def get_seed(
    seed_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(
        require_roles("owner", "admin", "viewer", "service_role")
    ),
) -> schemas.SeedRead:
    try:
        seed_uuid = uuid.UUID(seed_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid seed id") from exc

    result = await session.execute(select(models.Seed).where(models.Seed.id == seed_uuid))
    seed = result.scalar_one_or_none()
    if seed is None:
        raise HTTPException(status_code=404, detail="Seed not found")
    return schemas.SeedRead.from_orm(seed)

