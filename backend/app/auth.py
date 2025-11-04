"""Supabase Auth integration helpers for the FastAPI backend."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Iterable, Mapping, MutableMapping, Optional

import httpx
import jwt
from jwt import algorithms
from dotenv import find_dotenv, load_dotenv
from fastapi import Depends, Header, HTTPException, status
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings

# Ensure environment variables from ``.env`` are loaded when this module is
# imported. This mirrors the behavior used for the database configuration and
# keeps configuration in a single place for local development.
_DOTENV_PATH = find_dotenv(filename=".env", raise_error_if_not_found=False, usecwd=True)
if _DOTENV_PATH:
    load_dotenv(_DOTENV_PATH)


logger = logging.getLogger(__name__)


class SupabaseAuthSettings(BaseSettings):
    """Configuration required to validate Supabase access tokens."""

    supabase_url: str = Field(..., env="SUPABASE_URL")
    supabase_anon_key: str = Field(..., env="SUPABASE_ANON_KEY")
    supabase_jwt_audience: str = Field("authenticated", env="SUPABASE_JWT_AUDIENCE")
    supabase_jwt_issuer: Optional[str] = Field(None, env="SUPABASE_JWT_ISSUER")
    supabase_jwks_ttl_seconds: int = Field(3600, env="SUPABASE_JWKS_TTL_SECONDS")
    supabase_http_timeout_seconds: float = Field(5.0, env="SUPABASE_HTTP_TIMEOUT_SECONDS")
    supabase_jwt_secret: Optional[str] = Field(None, env="SUPABASE_JWT_SECRET")
    supabase_jwt_algorithm: str = Field("HS256", env="SUPABASE_JWT_ALGORITHM")


class SupabaseAuthError(RuntimeError):
    """Raised when Supabase authentication fails or cannot be validated."""


@lru_cache
def get_supabase_auth_settings() -> SupabaseAuthSettings:
    """Load and cache Supabase Auth settings from the environment."""

    try:
        return SupabaseAuthSettings()
    except ValidationError as exc:  # pragma: no cover - configuration error
        raise RuntimeError("Supabase Auth environment variables are not configured") from exc


class _JWKSCache:
    """Caches Supabase JWKS responses to avoid fetching keys on every request."""

    def __init__(
        self,
        jwks_url: str,
        ttl_seconds: int,
        timeout: float,
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._jwks_url = jwks_url
        self._ttl_seconds = ttl_seconds
        self._timeout = timeout
        self._lock = asyncio.Lock()
        self._expires_at: float = 0.0
        self._keys: dict[str, Mapping[str, Any]] = {}
        self._headers = dict(headers or {})

    async def _refresh(self) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(self._jwks_url, headers=self._headers or None)
            response.raise_for_status()
            payload = response.json()

        keys = {
            key["kid"]: key
            for key in payload.get("keys", [])
            if isinstance(key, Mapping) and "kid" in key
        }

        self._keys = keys
        self._expires_at = time.monotonic() + self._ttl_seconds

    async def get_key(self, kid: str) -> Mapping[str, Any]:
        async with self._lock:
            if time.monotonic() >= self._expires_at:
                await self._refresh()

            key = self._keys.get(kid)
            if key is None:
                # The requested key may have rotated. Refresh once more to be
                # certain before failing.
                await self._refresh()
                key = self._keys.get(kid)
                if key is None:
                    raise KeyError(kid)
            return key


def _ensure_mapping(*values: Any) -> Mapping[str, Any]:
    """Return the first mapping-like value from ``values`` or an empty dict."""

    for value in values:
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _collect_roles(*values: Any) -> tuple[str, ...]:
    """Collect and normalize role strings from multiple inputs."""

    roles: set[str] = set()
    for value in values:
        if isinstance(value, str) and value:
            roles.add(value.lower())
        elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            for item in value:
                if isinstance(item, str) and item:
                    roles.add(item.lower())
    if "authenticated" not in roles:
        roles.add("authenticated")
    return tuple(sorted(roles))


def _timestamp_to_datetime(timestamp: Any) -> datetime:
    if timestamp is None:
        raise SupabaseAuthError("Supabase access token is missing an expiration claim")
    try:
        numeric = float(timestamp)
    except (TypeError, ValueError) as exc:  # pragma: no cover - invalid token
        raise SupabaseAuthError("Supabase access token has an invalid timestamp") from exc
    return datetime.fromtimestamp(numeric, tz=timezone.utc)


@dataclass(frozen=True)
class SupabaseUser:
    """Representation of an authenticated Supabase user."""

    id: uuid.UUID
    email: Optional[str]
    role: str
    roles: tuple[str, ...]
    app_metadata: Mapping[str, Any]
    user_metadata: Mapping[str, Any]

    def has_role(self, role: str) -> bool:
        return role.lower() in self.roles

    def has_any_role(self, roles: Iterable[str]) -> bool:
        required = {role.lower() for role in roles}
        return any(role in required for role in self.roles)


@dataclass(frozen=True)
class SupabaseSession:
    """Authenticated Supabase session information."""

    user: SupabaseUser
    access_token: str
    expires_at: datetime
    issued_at: Optional[datetime]
    session_id: Optional[str]
    raw_claims: Mapping[str, Any]

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at


class SupabaseAuth:
    """Validates Supabase access tokens and fetches user information."""

    def __init__(self, settings: SupabaseAuthSettings) -> None:
        self._settings = settings
        jwks_url = settings.supabase_url.rstrip("/") + "/auth/v1/jwks"
        headers = {
            "apikey": settings.supabase_anon_key,
            "Authorization": f"Bearer {settings.supabase_anon_key}",
        }
        self._jwks_cache = _JWKSCache(
            jwks_url=jwks_url,
            ttl_seconds=settings.supabase_jwks_ttl_seconds,
            timeout=settings.supabase_http_timeout_seconds,
            headers=headers,
        )

    async def _decode_with_jwks(
        self,
        token: str,
        kid: str,
        issuer: str,
        audience: str,
    ) -> Mapping[str, Any]:
        try:
            key_data = await self._jwks_cache.get_key(kid)
        except httpx.HTTPError as exc:
            raise SupabaseAuthError("Unable to download Supabase signing keys") from exc
        except KeyError as exc:
            raise SupabaseAuthError("Supabase signing key not found; try logging in again") from exc

        rsa_algorithm = algorithms.get_default_algorithms().get("RS256")
        if rsa_algorithm is None:  # pragma: no cover - algorithm missing in PyJWT build
            raise SupabaseAuthError("Supabase RSA algorithm support is unavailable")

        try:
            rsa_key = rsa_algorithm.from_jwk(json.dumps(dict(key_data)))
        except (TypeError, ValueError) as exc:  # pragma: no cover - invalid JWKS response
            raise SupabaseAuthError("Supabase signing key is invalid") from exc

        try:
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                audience=audience,
                issuer=issuer,
            )
        except jwt.ExpiredSignatureError as exc:
            raise SupabaseAuthError("Supabase access token has expired") from exc
        except jwt.PyJWTError as exc:
            raise SupabaseAuthError("Supabase access token validation failed") from exc

        return payload

    def _decode_with_shared_secret(
        self,
        token: str,
        issuer: str,
        audience: str,
        algorithm_from_header: Optional[str],
    ) -> Mapping[str, Any]:
        secret = self._settings.supabase_jwt_secret
        if not secret:
            raise SupabaseAuthError("Supabase JWT secret fallback is not configured")

        algorithm = self._settings.supabase_jwt_algorithm or "HS256"
        if algorithm_from_header and algorithm_from_header != algorithm:
            raise SupabaseAuthError(
                "Supabase access token algorithm does not match the configured shared secret algorithm"
            )

        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=[algorithm],
                audience=audience,
                issuer=issuer,
            )
        except jwt.ExpiredSignatureError as exc:
            raise SupabaseAuthError("Supabase access token has expired") from exc
        except jwt.PyJWTError as exc:
            raise SupabaseAuthError("Supabase access token validation failed") from exc

        return payload

    async def _decode_token(self, token: str) -> Mapping[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise SupabaseAuthError("Supabase access token is malformed") from exc

        issuer = self._settings.supabase_jwt_issuer or (
            self._settings.supabase_url.rstrip("/") + "/auth/v1"
        )
        audience = self._settings.supabase_jwt_audience
        kid = header.get("kid")
        last_error: Optional[SupabaseAuthError] = None

        if kid:
            try:
                return await self._decode_with_jwks(token, kid, issuer, audience)
            except SupabaseAuthError as exc:
                last_error = exc

        if self._settings.supabase_jwt_secret:
            try:
                return self._decode_with_shared_secret(
                    token,
                    issuer=issuer,
                    audience=audience,
                    algorithm_from_header=header.get("alg"),
                )
            except SupabaseAuthError as exc:
                last_error = exc

        if last_error is not None:
            raise last_error

        if not kid:
            raise SupabaseAuthError(
                "Supabase access token is missing a key id and no shared secret fallback is configured"
            )

        raise SupabaseAuthError("Supabase access token validation failed")

    async def _fetch_user(self, token: str) -> Mapping[str, Any]:
        headers = {
            "authorization": f"Bearer {token}",
            "apikey": self._settings.supabase_anon_key,
        }
        url = self._settings.supabase_url.rstrip("/") + "/auth/v1/user"

        async with httpx.AsyncClient(timeout=self._settings.supabase_http_timeout_seconds) as client:
            response = await client.get(url, headers=headers)

        if response.status_code != 200:
            raise SupabaseAuthError("Supabase session is not valid; please sign in again")

        payload = response.json()
        if not isinstance(payload, MutableMapping):  # pragma: no cover - unexpected API response
            raise SupabaseAuthError("Unexpected response from Supabase Auth user endpoint")
        return payload

    @staticmethod
    def _parse_user_id(claims: Mapping[str, Any], user_data: Mapping[str, Any]) -> uuid.UUID:
        user_id_value = user_data.get("id") or claims.get("sub")
        if user_id_value is None:
            raise SupabaseAuthError("Supabase access token is missing a user id")
        try:
            return uuid.UUID(str(user_id_value))
        except (TypeError, ValueError) as exc:
            raise SupabaseAuthError("Supabase user id is not a valid UUID") from exc

    def _build_user(self, claims: Mapping[str, Any], user_data: Mapping[str, Any]) -> SupabaseUser:
        user_id = self._parse_user_id(claims, user_data)
        email = user_data.get("email") or claims.get("email")
        role_value = user_data.get("role") or claims.get("role") or "authenticated"
        roles = _collect_roles(
            role_value,
            user_data.get("app_metadata", {}).get("roles") if isinstance(user_data.get("app_metadata"), Mapping) else None,
            claims.get("app_metadata", {}).get("roles") if isinstance(claims.get("app_metadata"), Mapping) else None,
        )
        app_metadata = _ensure_mapping(user_data.get("app_metadata"), claims.get("app_metadata"))
        user_metadata = _ensure_mapping(user_data.get("user_metadata"), claims.get("user_metadata"))
        return SupabaseUser(
            id=user_id,
            email=email,
            role=str(role_value),
            roles=roles,
            app_metadata=app_metadata,
            user_metadata=user_metadata,
        )

    async def get_session(self, token: str) -> SupabaseSession:
        """Validate ``token`` and return session metadata."""

        claims = await self._decode_token(token)
        user_data = await self._fetch_user(token)
        user = self._build_user(claims, user_data)

        expires_at = _timestamp_to_datetime(claims.get("exp"))
        issued_at = None
        if "iat" in claims:
            try:
                issued_at = _timestamp_to_datetime(claims.get("iat"))
            except SupabaseAuthError:
                issued_at = None

        session_identifier = (
            claims.get("session_id")
            or claims.get("sid")
            or user_data.get("session_id")
        )

        return SupabaseSession(
            user=user,
            access_token=token,
            expires_at=expires_at,
            issued_at=issued_at,
            session_id=str(session_identifier) if session_identifier else None,
            raw_claims=dict(claims),
        )


@lru_cache
def get_supabase_auth() -> SupabaseAuth:
    """Return a cached ``SupabaseAuth`` instance for dependency injection."""

    return SupabaseAuth(get_supabase_auth_settings())


async def get_current_supabase_session(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    auth: SupabaseAuth = Depends(get_supabase_auth),
) -> SupabaseSession:
    """FastAPI dependency that resolves the current Supabase session."""

    if not authorization:
        logger.warning(
            "Supabase auth failed: missing Authorization header for protected endpoint",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is missing",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        logger.warning(
            "Supabase auth failed: invalid Authorization header format (scheme=%s, has_token=%s)",
            scheme.lower(),
            bool(token),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be a Bearer token",
        )

    try:
        session = await auth.get_session(token)
    except SupabaseAuthError as exc:
        logger.warning("Supabase auth failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return session


async def require_authenticated_session(
    session: SupabaseSession = Depends(get_current_supabase_session),
) -> SupabaseSession:
    """Ensure the Supabase session is active and not expired."""

    if session.is_expired:
        logger.warning(
            "Supabase auth failed: access token expired for user_id=%s",
            session.user.id,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Supabase session has expired")
    return session


def require_roles(*roles: str):
    """Factory that returns a dependency enforcing one of ``roles`` is present."""

    if not roles:
        raise ValueError("At least one role must be provided to require_roles")

    async def dependency(session: SupabaseSession = Depends(require_authenticated_session)) -> SupabaseSession:
        if not session.user.has_any_role(roles):
            logger.warning(
                "Supabase auth failed: user_id=%s missing required role (required=%s, user_roles=%s)",
                session.user.id,
                roles,
                session.user.roles,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return session

    return dependency
