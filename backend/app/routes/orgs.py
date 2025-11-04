"""Endpoints for managing organizations."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models, schemas
from ..auth import SupabaseSession, require_roles
from ..database import get_session
from ..services.supabase_memberships import ensure_org_membership

router = APIRouter(prefix="/api/orgs", tags=["orgs"])


@router.post("", response_model=schemas.OrgRead, status_code=201)
async def create_org(
    payload: schemas.OrgCreate,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> schemas.OrgRead:
    existing = await session.execute(select(models.Org).where(models.Org.name == payload.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Organization with this name already exists")

    org = models.Org(name=payload.name)
    session.add(org)
    await session.flush()

    await ensure_org_membership(session, org.id, current_session, role="owner", approve=True)

    await session.commit()
    await session.refresh(org)
    return schemas.OrgRead.from_orm(org)


@router.get("/{org_id}", response_model=schemas.OrgRead)
async def get_org(
    org_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(
        require_roles("owner", "admin", "viewer", "service_role")
    ),
) -> schemas.OrgRead:
    try:
        org_uuid = uuid.UUID(org_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid organization id") from exc

    result = await session.execute(select(models.Org).where(models.Org.id == org_uuid))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return schemas.OrgRead.from_orm(org)

