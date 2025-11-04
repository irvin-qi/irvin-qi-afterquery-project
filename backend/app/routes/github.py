"""Routes for managing GitHub App installations."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models, schemas
from ..auth import SupabaseSession, require_roles
from ..database import get_session
from ..github_app import GitHubAppError, get_github_app_client, get_github_app_settings
from ..services.github_installations import github_installation_to_schema
from ..services.supabase_memberships import require_org_membership_role

router = APIRouter(prefix="/api/github", tags=["github"])


def _normalize_return_path(candidate: Optional[str]) -> Optional[str]:
    """Limit redirects to in-app paths while preserving query strings."""

    if not candidate:
        return None

    trimmed = candidate.strip()
    if not trimmed:
        return None

    if trimmed.startswith(("http://", "https://")):
        parsed = urlsplit(trimmed)
        path = parsed.path or "/"
        if not path.startswith("/"):
            path = f"/{path.lstrip('/')}"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        if parsed.fragment:
            path = f"{path}#{parsed.fragment}"
        trimmed = path

    if not trimmed.startswith("/"):
        trimmed = f"/{trimmed.lstrip('/')}"

    if len(trimmed) > 512:
        trimmed = trimmed[:512]

    return trimmed


def _normalize_redirect_url(candidate: Optional[str]) -> Optional[str]:
    """Validate the GitHub installation redirect URL."""

    if not candidate:
        return None

    trimmed = candidate.strip()
    if not trimmed:
        return None

    parsed = urlsplit(trimmed)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if parsed.query:
        normalized = f"{normalized}?{parsed.query}"
    if parsed.fragment:
        normalized = f"{normalized}#{parsed.fragment}"

    return normalized


@router.post(
    "/installations/start",
    response_model=schemas.GitHubInstallationStartResponse,
)
async def start_github_installation(
    payload: schemas.GitHubInstallationStartRequest,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(
        require_roles("authenticated", "service_role")
    ),
) -> schemas.GitHubInstallationStartResponse:
    org_id = payload.org_id
    return_path = _normalize_return_path(payload.return_path)
    redirect_url = _normalize_redirect_url(payload.redirect_url)

    org_result = await session.execute(
        select(models.Org).where(models.Org.id == org_id)
    )
    org = org_result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    if not current_session.user.has_role("service_role"):
        await require_org_membership_role(
            session,
            org_id,
            current_session,
            allowed_roles=("owner", "admin"),
        )

    await session.execute(
        delete(models.GitHubInstallationState).where(
            models.GitHubInstallationState.org_id == org_id
        )
    )

    state_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    state = models.GitHubInstallationState(
        token=state_token,
        org_id=org_id,
        expires_at=expires_at,
        return_path=return_path,
    )
    session.add(state)
    await session.commit()

    settings = get_github_app_settings()
    try:
        app_slug = settings.require_app_slug()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    query_params = {"state": state_token}
    if redirect_url:
        query_params["redirect_url"] = redirect_url

    installation_url = (
        f"https://github.com/apps/{app_slug}/installations/new?"
        f"{urlencode(query_params)}"
    )
    return schemas.GitHubInstallationStartResponse(installation_url=installation_url)


@router.post(
    "/installations/complete",
    response_model=schemas.GitHubInstallationCompleteResponse,
)
async def complete_github_installation(
    payload: schemas.GitHubInstallationCompleteRequest,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(
        require_roles("authenticated", "service_role")
    ),
) -> schemas.GitHubInstallationCompleteResponse:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("🔵 /installations/complete endpoint called with payload: %s", payload.dict())
    
    state_token = payload.state.strip()
    if not state_token:
        logger.warning("❌ State token is missing in request")
        raise HTTPException(status_code=400, detail="State token is required")

    state_result = await session.execute(
        select(models.GitHubInstallationState).where(
            models.GitHubInstallationState.token == state_token
        )
    )
    state = state_result.scalar_one_or_none()
    if state is None:
        raise HTTPException(status_code=400, detail="Installation state not found")

    now = datetime.now(timezone.utc)
    if state.expires_at < now:
        await session.delete(state)
        await session.commit()
        raise HTTPException(status_code=410, detail="Installation link expired")

    org_id = state.org_id
    if not current_session.user.has_role("service_role"):
        await require_org_membership_role(
            session,
            org_id,
            current_session,
            allowed_roles=("owner", "admin"),
        )

    github_app = get_github_app_client()
    try:
        installation_payload = await github_app.fetch_installation(
            payload.installation_id
        )
    except GitHubAppError as exc:  # pragma: no cover - network failure
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    account = installation_payload.get("account")
    if not isinstance(account, dict):
        raise HTTPException(
            status_code=502, detail="GitHub installation response was malformed"
        )

    target_type = installation_payload.get("target_type") or account.get("type")
    if target_type != "Organization":
        raise HTTPException(
            status_code=400,
            detail="Install the GitHub App on an organization, not a user account",
        )

    account_login = account.get("login")
    if not isinstance(account_login, str) or not account_login.strip():
        raise HTTPException(
            status_code=502, detail="GitHub account login missing from installation"
        )

    account_id_raw = account.get("id")
    if isinstance(account_id_raw, str):
        try:
            account_id = int(account_id_raw)
        except ValueError:  # pragma: no cover - defensive parsing
            account_id = None
    else:
        account_id = account_id_raw

    if not isinstance(account_id, int):
        raise HTTPException(
            status_code=502, detail="GitHub account id missing from installation"
        )

    account_avatar_url = account.get("avatar_url")
    account_html_url = account.get("html_url")
    installation_html_url = installation_payload.get("html_url")

    upsert_values = {
        "org_id": org_id,
        "installation_id": payload.installation_id,
        "target_type": target_type,
        "account_login": account_login,
        "account_id": account_id,
        "account_avatar_url": account_avatar_url,
        "account_html_url": account_html_url,
        "installation_html_url": installation_html_url,
        "updated_at": now,
    }

    update_values = {key: value for key, value in upsert_values.items() if key != "org_id"}

    insert_stmt = (
        pg_insert(models.GitHubInstallation)
        .values(**upsert_values)
        .on_conflict_do_update(
            index_elements=[models.GitHubInstallation.org_id],
            set_=update_values,
        )
        .returning(models.GitHubInstallation)
    )

    result = await session.execute(insert_stmt)
    installation_model = result.scalar_one()

    return_path = _normalize_return_path(state.return_path)

    await session.delete(state)
    await session.commit()
    await session.refresh(installation_model)

    return schemas.GitHubInstallationCompleteResponse(
        installation=github_installation_to_schema(installation_model),
        return_path=return_path,
    )
