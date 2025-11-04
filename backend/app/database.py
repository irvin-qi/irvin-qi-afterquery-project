"""Database configuration for the FastAPI backend.

This module provides a SQLAlchemy async engine and session factory that connect to
Supabase Postgres using the DATABASE_URL environment variable. Supabase issues
Postgres connection strings that require the ``postgresql`` dialect. To take
advantage of SQLAlchemy's async support we convert the DSN to the
``postgresql+asyncpg`` driver if needed.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import find_dotenv, load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from . import migrations

logger = logging.getLogger(__name__)

# Load DATABASE_URL and other environment variables from the project root ``.env``
# file, if present. ``find_dotenv`` walks up from the current working directory,
# so it will locate the repository-level configuration even when this module is
# imported from nested packages.
_DOTENV_PATH = find_dotenv(filename=".env", raise_error_if_not_found=False, usecwd=True)
if _DOTENV_PATH:
    load_dotenv(_DOTENV_PATH)

_DATABASE_URL_ENV = "DATABASE_URL"


def _build_async_database_url(raw_url: str) -> str:
    """Ensure the database URL uses the asyncpg driver."""

    if raw_url.startswith("postgresql+asyncpg://"):
        return raw_url
    if raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql://", 1)
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw_url


def _is_pooled_connection(url: str) -> bool:
    """Check if the URL is for a pooled connection (PgBouncer/Supavisor)."""
    # Pooled connections typically use port 6543 (transaction mode) or 5432 (session mode)
    # Also check for pooled hostnames like aws-0-<region>.pooler.supabase.com
    pooled_indicators = [
        ".pooler.supabase.com",
        "pgbouncer=true",
        "supavisor",
    ]
    return any(indicator in url for indicator in pooled_indicators)


def get_database_url() -> str:
    try:
        raw_url = os.environ[_DATABASE_URL_ENV]
    except KeyError as exc:  # pragma: no cover - configuration error should be explicit
        raise RuntimeError(
            "DATABASE_URL environment variable must be set to connect to Supabase"
        ) from exc
    return _build_async_database_url(raw_url)


def get_engine_kwargs(url: str) -> dict:
    """Get engine configuration based on connection type."""
    kwargs = {
        "echo": False,
        # Connection pool settings for better performance
        "pool_size": 5,
        "max_overflow": 10,
        "pool_pre_ping": True,  # Verify connections before using them
        "pool_recycle": 3600,   # Recycle connections after 1 hour
    }
    
    # Session mode pooler (port 5432) supports prepared statements, so no need to disable them
    # Transaction mode (port 6543) would need statement_cache_size: 0
    is_pooled = _is_pooled_connection(url)
    if is_pooled and ":6543" in url:
        # Transaction mode pooler - disable prepared statements
        logger.info("Using transaction mode pooled connection - disabling prepared statements")
        kwargs.update({
            "connect_args": {
                "statement_cache_size": 0,
            }
        })
    else:
        logger.info("Database configured: prepared statements enabled")
    
    return kwargs


_database_url = get_database_url()
ASYNC_ENGINE = create_async_engine(_database_url, **get_engine_kwargs(_database_url))
ASYNC_SESSION_FACTORY = async_sessionmaker(
    ASYNC_ENGINE, expire_on_commit=False, class_=AsyncSession
)


@asynccontextmanager
async def lifespan(app):  # pragma: no cover - FastAPI hook
    """Ensure the database engine is disposed when the app shuts down."""

    try:
        applied, _ = await migrations.ensure_schema(ASYNC_ENGINE)
        if applied:
            logger.info("Database schema applied during startup")
    except RuntimeError as exc:
        logger.exception("Failed to apply database schema during startup")
        raise

    yield
    await ASYNC_ENGINE.dispose()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an ``AsyncSession``."""

    async with ASYNC_SESSION_FACTORY() as session:
        yield session

