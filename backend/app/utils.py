"""Utility helpers for token generation and hashing."""

from __future__ import annotations

import hashlib
import secrets

TOKEN_BYTES = 32


def generate_token() -> str:
    """Generate a URL-safe token for invitations or repo access."""

    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(raw_token: str) -> str:
    """Generate a SHA-256 hash for storing an opaque token."""

    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

