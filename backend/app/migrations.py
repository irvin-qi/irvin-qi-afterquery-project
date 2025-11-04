"""Utilities for applying the database schema at runtime."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

LOGGER = logging.getLogger(__name__)



def _detect_schema_path() -> Path:
    """Locate the schema file relative to the current module."""

    env_override = os.environ.get("APP_SCHEMA_PATH")
    if env_override:
        return Path(env_override)

    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "db" / "schema.sql"
        if candidate.exists():
            return candidate

    # Fallback to the historical location two levels up; this keeps behaviour
    # unchanged for environments that intentionally manage the schema file
    # elsewhere and rely on the error handling below when it is missing.
    try:
        return current.parents[2] / "db" / "schema.sql"
    except IndexError:  # pragma: no cover - defensive fallback
        return current.parent / "db" / "schema.sql"


SCHEMA_PATH = _detect_schema_path()

_MIGRATION_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS app_schema_migrations ("
    " schema_hash text PRIMARY KEY,"
    " applied_at timestamptz NOT NULL DEFAULT now()"
    ")"
)


def _load_schema_sql() -> str:
    try:
        return SCHEMA_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:  # pragma: no cover - developer misconfiguration
        raise RuntimeError("Database schema file not found") from exc


def _split_statements(schema_sql: str) -> Iterable[str]:
    return (stmt.strip() for stmt in schema_sql.split(";") if stmt.strip())


async def ensure_schema(engine: AsyncEngine) -> tuple[bool, int]:
    """Apply the schema SQL file if it has not been applied yet."""

    schema_sql = _load_schema_sql()
    if not schema_sql.strip():
        return False, 0

    schema_hash = hashlib.sha256(schema_sql.encode("utf-8")).hexdigest()
    statements = list(_split_statements(schema_sql))

    if not statements:
        return False, 0

    async with engine.begin() as conn:
        await conn.exec_driver_sql(_MIGRATION_TABLE_SQL)

        result = await conn.execute(
            text(
                "SELECT 1 FROM app_schema_migrations"
                " WHERE schema_hash = :schema_hash"
            ),
            {"schema_hash": schema_hash},
        )
        if result.first() is not None:
            LOGGER.debug("Database schema already applied (hash=%s)", schema_hash)
            return False, 0

        for statement in statements:
            await conn.exec_driver_sql(statement)

        insert_result = await conn.execute(
            text(
                "INSERT INTO app_schema_migrations (schema_hash)"
                " VALUES (:schema_hash)"
                " ON CONFLICT DO NOTHING"
            ),
            {"schema_hash": schema_hash},
        )

    applied = bool(insert_result.rowcount and insert_result.rowcount > 0)

    if applied:
        LOGGER.info(
            "Applied database schema (%d statements, hash=%s)",
            len(statements),
            schema_hash,
        )
        return True, len(schema_sql)

    LOGGER.debug(
        "Database schema already applied by another process (hash=%s)",
        schema_hash,
    )
    return False, 0
