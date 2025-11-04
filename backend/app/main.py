from __future__ import annotations

import logging
import os
from typing import Iterable, Optional
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .database import lifespan
from .routes import admin, assessments, assessment_features, candidate, github, invitations, orgs, reviews, scheduling, seeds

app = FastAPI(title="Backend API", lifespan=lifespan)

logger = logging.getLogger(__name__)


def _normalize_origin(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    parsed = urlsplit(trimmed)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _collect_cors_origins() -> list[str]:
    origin_keys: Iterable[str] = ("FRONTEND_APP_URL", "CANDIDATE_APP_URL", "SUPABASE_URL")
    origins = {
        origin
        for origin in (
            _normalize_origin(os.getenv(key))
            for key in origin_keys
        )
        if origin
    }

    extra_origins = os.getenv("ADDITIONAL_CORS_ORIGINS")
    if extra_origins:
        for candidate in extra_origins.split(","):
            normalized = _normalize_origin(candidate)
            if normalized:
                origins.add(normalized)

    if not origins:
        # Fall back to local development defaults when nothing is configured.
        origins.update(
            {
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            }
        )
        logger.debug(
            "CORS origins not configured; defaulting to local development origins: %s",
            sorted(origins),
        )
    else:
        logger.debug("Configured CORS origins: %s", sorted(origins))

    return sorted(origins)


allowed_origins = _collect_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# Add exception handlers to ensure CORS headers are included even on errors
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Ensure CORS headers are included in HTTP exception responses."""
    headers = {}
    origin = request.headers.get("origin")
    if origin and origin in allowed_origins:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Ensure CORS headers are included in validation error responses."""
    headers = {}
    origin = request.headers.get("origin")
    if origin and origin in allowed_origins:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
        headers=headers,
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Ensure CORS headers are included in general exception responses."""
    import traceback
    error_detail = str(exc)
    logger.error(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    
    headers = {}
    origin = request.headers.get("origin")
    if origin and origin in allowed_origins:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    
    # In development, return the actual error message for debugging
    # In production, you might want to hide this
    import os
    is_dev = os.getenv("ENVIRONMENT", "development").lower() in ("development", "dev", "local")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": error_detail if is_dev else "Internal server error",
            "type": type(exc).__name__,
        },
        headers=headers,
    )

app.include_router(admin.router)
app.include_router(orgs.router)
app.include_router(seeds.router)
app.include_router(assessments.router)
app.include_router(assessment_features.router)
app.include_router(invitations.router)
app.include_router(candidate.router)
app.include_router(github.router)
app.include_router(reviews.router)
app.include_router(scheduling.router)


@app.get("/")
async def root():
    return {"message": "Backend is running 🚀"}
