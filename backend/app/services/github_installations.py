"""Utilities for managing GitHub App installations scoped to organizations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models, schemas
from ..github_app import GitHubAppClient, get_github_app_client

_GITHUB_INSTALLATION_REQUIRED = (
    "Connect the GitHub App to this project before performing GitHub actions."
)


async def get_github_installation(
    session: AsyncSession, org_id: UUID
) -> Optional[models.GitHubInstallation]:
    result = await session.execute(
        select(models.GitHubInstallation).where(models.GitHubInstallation.org_id == org_id)
    )
    return result.scalar_one_or_none()


async def require_github_installation(
    session: AsyncSession, org_id: UUID
) -> models.GitHubInstallation:
    installation = await get_github_installation(session, org_id)
    if installation is None:
        raise HTTPException(status_code=409, detail=_GITHUB_INSTALLATION_REQUIRED)
    return installation


async def require_github_installation_client(
    session: AsyncSession, org_id: UUID
) -> GitHubAppClient:
    installation = await require_github_installation(session, org_id)
    base_client = get_github_app_client()
    return base_client.with_installation(
        installation.installation_id, installation.account_login
    )


def github_installation_to_schema(
    installation: Optional[models.GitHubInstallation],
) -> schemas.AdminGitHubInstallation:
    if installation is None:
        return schemas.AdminGitHubInstallation(
            connected=False,
            installation_id=None,
            account_login=None,
            account_html_url=None,
            installation_html_url=None,
            target_type=None,
            connected_at=None,
        )

    connected_at = installation.created_at
    if isinstance(installation.created_at, datetime):
        connected_at = installation.created_at
    else:  # pragma: no cover - defensive fallback
        connected_at = datetime.now(timezone.utc)

    return schemas.AdminGitHubInstallation(
        connected=True,
        installation_id=installation.installation_id,
        account_login=installation.account_login,
        account_html_url=installation.account_html_url,
        installation_html_url=installation.installation_html_url,
        target_type=installation.target_type,
        connected_at=connected_at,
    )
