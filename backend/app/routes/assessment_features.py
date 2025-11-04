"""Assessment feature endpoints for managing scoring criteria."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import models, schemas
from ..auth import SupabaseSession, require_roles
from ..database import get_session
from ..services.supabase_memberships import require_org_membership_role

router = APIRouter(prefix="/api/assessments/{assessment_id}/features", tags=["assessment-features"])


async def _get_assessment_and_verify_access(
    assessment_id: uuid.UUID,
    session: AsyncSession,
    current_session: SupabaseSession,
    allowed_roles: tuple[str, ...] = ("owner", "admin", "viewer"),
) -> models.Assessment:
    """Helper to get assessment and verify user has access."""
    result = await session.execute(
        select(models.Assessment)
        .where(models.Assessment.id == assessment_id)
    )
    assessment = result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    await require_org_membership_role(
        session,
        assessment.org_id,
        current_session,
        allowed_roles=allowed_roles,
    )
    return assessment


@router.post("", response_model=schemas.AssessmentFeatureRead, status_code=201)
async def create_assessment_feature(
    assessment_id: str,
    payload: schemas.AssessmentFeatureCreate,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> schemas.AssessmentFeatureRead:
    """Create a new feature for an assessment."""
    try:
        assessment_uuid = uuid.UUID(assessment_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid assessment id") from exc

    # Verify assessment exists and user has access
    assessment = await _get_assessment_and_verify_access(
        assessment_uuid, session, current_session, allowed_roles=("owner", "admin")
    )

    # Check if feature with same name already exists
    existing = await session.execute(
        select(models.AssessmentFeature).where(
            models.AssessmentFeature.assessment_id == assessment_uuid,
            models.AssessmentFeature.name == payload.name,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Feature with name '{payload.name}' already exists for this assessment",
        )

    feature = models.AssessmentFeature(
        assessment_id=assessment_uuid,
        name=payload.name,
        description=payload.description,
        weight=payload.weight,
    )
    session.add(feature)
    await session.commit()
    await session.refresh(feature)
    return schemas.AssessmentFeatureRead.from_orm(feature)


@router.get("", response_model=list[schemas.AssessmentFeatureRead])
async def list_assessment_features(
    assessment_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(
        require_roles("authenticated", "service_role", "owner", "admin", "viewer")
    ),
) -> list[schemas.AssessmentFeatureRead]:
    """List all features for an assessment, ordered by display_order."""
    try:
        assessment_uuid = uuid.UUID(assessment_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid assessment id") from exc

    # Verify assessment exists and user has access
    await _get_assessment_and_verify_access(
        assessment_uuid, session, current_session, allowed_roles=("owner", "admin", "viewer")
    )

    result = await session.execute(
        select(models.AssessmentFeature)
        .where(models.AssessmentFeature.assessment_id == assessment_uuid)
        .order_by(models.AssessmentFeature.weight.desc(), models.AssessmentFeature.name)
    )
    features = result.scalars().all()
    return [schemas.AssessmentFeatureRead.from_orm(f) for f in features]


@router.get("/{feature_id}", response_model=schemas.AssessmentFeatureRead)
async def get_assessment_feature(
    assessment_id: str,
    feature_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(
        require_roles("authenticated", "service_role", "owner", "admin", "viewer")
    ),
) -> schemas.AssessmentFeatureRead:
    """Get a single feature by ID."""
    try:
        assessment_uuid = uuid.UUID(assessment_id)
        feature_uuid = uuid.UUID(feature_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid id") from exc

    # Verify assessment exists and user has access
    await _get_assessment_and_verify_access(
        assessment_uuid, session, current_session, allowed_roles=("owner", "admin", "viewer")
    )

    result = await session.execute(
        select(models.AssessmentFeature).where(
            models.AssessmentFeature.id == feature_uuid,
            models.AssessmentFeature.assessment_id == assessment_uuid,
        )
    )
    feature = result.scalar_one_or_none()
    if feature is None:
        raise HTTPException(status_code=404, detail="Feature not found")
    return schemas.AssessmentFeatureRead.from_orm(feature)


@router.patch("/{feature_id}", response_model=schemas.AssessmentFeatureRead)
async def update_assessment_feature(
    assessment_id: str,
    feature_id: str,
    payload: schemas.AssessmentFeatureUpdate,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> schemas.AssessmentFeatureRead:
    """Update a feature."""
    try:
        assessment_uuid = uuid.UUID(assessment_id)
        feature_uuid = uuid.UUID(feature_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid id") from exc

    # Verify assessment exists and user has access
    await _get_assessment_and_verify_access(
        assessment_uuid, session, current_session, allowed_roles=("owner", "admin")
    )

    result = await session.execute(
        select(models.AssessmentFeature).where(
            models.AssessmentFeature.id == feature_uuid,
            models.AssessmentFeature.assessment_id == assessment_uuid,
        )
    )
    feature = result.scalar_one_or_none()
    if feature is None:
        raise HTTPException(status_code=404, detail="Feature not found")

    # Check for name conflict if name is being updated
    if payload.name is not None and payload.name != feature.name:
        existing = await session.execute(
            select(models.AssessmentFeature).where(
                models.AssessmentFeature.assessment_id == assessment_uuid,
                models.AssessmentFeature.name == payload.name,
                models.AssessmentFeature.id != feature_uuid,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Feature with name '{payload.name}' already exists for this assessment",
            )

    # Update fields
    if payload.name is not None:
        feature.name = payload.name
    if payload.description is not None:
        feature.description = payload.description
    if payload.weight is not None:
        feature.weight = payload.weight

    await session.commit()
    await session.refresh(feature)
    return schemas.AssessmentFeatureRead.from_orm(feature)


@router.delete("/{feature_id}", status_code=204)
async def delete_assessment_feature(
    assessment_id: str,
    feature_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> None:
    """Delete a feature. This will cascade delete all related scores."""
    try:
        assessment_uuid = uuid.UUID(assessment_id)
        feature_uuid = uuid.UUID(feature_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid id") from exc

    # Verify assessment exists and user has access
    await _get_assessment_and_verify_access(
        assessment_uuid, session, current_session, allowed_roles=("owner", "admin")
    )

    result = await session.execute(
        select(models.AssessmentFeature).where(
            models.AssessmentFeature.id == feature_uuid,
            models.AssessmentFeature.assessment_id == assessment_uuid,
        )
    )
    feature = result.scalar_one_or_none()
    if feature is None:
        raise HTTPException(status_code=404, detail="Feature not found")

    await session.delete(feature)
    await session.commit()

