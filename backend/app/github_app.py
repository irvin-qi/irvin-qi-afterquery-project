"""GitHub App integration helpers.

This module centralizes all GitHub interactions required for the
assessment workflow.  It is intentionally lightweight so the rest of the
application can depend on a single abstraction without worrying about
authentication, request throttling, or small API differences.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import urlparse

import base64
import httpx
import jwt
from dotenv import find_dotenv, load_dotenv
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings


_DOTENV_PATH = find_dotenv(filename=".env", raise_error_if_not_found=False, usecwd=True)
if _DOTENV_PATH:
    load_dotenv(_DOTENV_PATH)


class GitHubAppSettings(BaseSettings):
    """Configuration required to interact with the GitHub App."""

    app_id: str = Field(..., alias="github_app_id", env="GITHUB_APP_ID")
    private_key: str = Field(..., alias="github_app_private_key", env="GITHUB_APP_PRIVATE_KEY")
    app_slug: Optional[str] = Field(
        None, alias="github_app_slug", env="GITHUB_APP_SLUG"
    )
    api_base_url: str = Field("https://api.github.com", env="GITHUB_API_BASE_URL")
    request_timeout_seconds: float = Field(15.0, env="GITHUB_HTTP_TIMEOUT_SECONDS")
    seed_repo_prefix: str = Field("afterquery-seed", env="GITHUB_SEED_PREFIX")
    candidate_repo_prefix: str = Field("afterquery-candidate", env="GITHUB_CANDIDATE_PREFIX")

    def normalized_private_key(self) -> str:
        """Return the private key with escaped newlines restored."""

        key = self.private_key.strip()
        if "\\n" in key:
            key = key.replace("\\n", "\n")
        if "-----BEGIN" not in key:
            try:
                decoded = base64.b64decode(key)
                key_candidate = decoded.decode("utf-8")
                if "-----BEGIN" in key_candidate:
                    key = key_candidate
            except Exception:  # pragma: no cover - best effort fallback
                pass
        if "-----BEGIN" not in key:
            key = key.encode("utf-8").decode("unicode_escape")
        return key

    def require_app_slug(self) -> str:
        """Return the configured GitHub App slug or raise a helpful error."""

        if not self.app_slug:
            raise RuntimeError(
                "GitHub App slug is not configured; set the GITHUB_APP_SLUG environment variable"
            )
        return self.app_slug


@lru_cache
def get_github_app_settings() -> GitHubAppSettings:
    try:
        return GitHubAppSettings()  # type: ignore[call-arg]
    except ValidationError as exc:  # pragma: no cover - configuration error
        raise RuntimeError("GitHub App environment variables are not configured") from exc


class GitHubAppError(RuntimeError):
    """Raised when a GitHub API request fails."""


@dataclass(slots=True)
class GitHubRepository:
    """A minimal representation of a GitHub repository."""

    id: int
    full_name: str
    html_url: Optional[str]
    default_branch: str
    clone_url: Optional[str]


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return normalized or "repo"


def _parse_repo_identifier(source: str) -> tuple[str, str]:
    """Return ``(owner, name)`` for a GitHub repo reference."""

    trimmed = source.strip()
    if not trimmed:
        raise ValueError("Repository reference cannot be empty")

    if trimmed.startswith("http://") or trimmed.startswith("https://"):
        parsed = urlparse(trimmed)
        path = parsed.path.strip("/")
        segments = [segment for segment in path.split("/") if segment]
    else:
        segments = [segment for segment in trimmed.split("/") if segment]

    if len(segments) < 2:
        raise ValueError("GitHub repository reference must include owner and name")

    owner, name = segments[0], segments[1]
    if name.endswith(".git"):
        name = name[:-4]
    return owner, name


class GitHubAppClient:
    """Lightweight wrapper for GitHub App installation interactions."""

    def __init__(
        self,
        settings: GitHubAppSettings,
        *,
        installation_id: Optional[int] = None,
        organization: Optional[str] = None,
        private_key: Optional[str] = None,
    ) -> None:
        self._settings = settings
        self._installation_id = installation_id
        self._organization = organization
        self._private_key = private_key or settings.normalized_private_key()
        self._app_jwt: Optional[str] = None
        self._app_jwt_expires_at: float = 0.0
        self._installation_token: Optional[str] = None
        self._installation_token_expires_at: float = 0.0

    @property
    def organization(self) -> str:
        if not self._organization:
            raise RuntimeError("GitHub App organization is not configured")
        return self._organization

    @property
    def installation_id(self) -> int:
        if self._installation_id is None:
            raise RuntimeError("GitHub App installation is not configured")
        return self._installation_id

    def with_installation(self, installation_id: int, organization: str) -> "GitHubAppClient":
        client = GitHubAppClient(
            self._settings,
            installation_id=installation_id,
            organization=organization,
            private_key=self._private_key,
        )
        client._app_jwt = self._app_jwt
        client._app_jwt_expires_at = self._app_jwt_expires_at
        return client

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        token: str,
        token_is_app: bool = False,
        expected_status: Sequence[int] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers = dict(headers)
        headers.setdefault("Accept", "application/vnd.github+json")
        headers.setdefault("User-Agent", "afterquery-app/seed-manager")
        if token_is_app:
            headers["Authorization"] = f"Bearer {token}"
        else:
            headers["Authorization"] = f"token {token}"

        response = await client.request(method, path, headers=headers, **kwargs)
        if expected_status and response.status_code not in expected_status:
            detail = response.text
            raise GitHubAppError(
                f"GitHub API request to {path} failed with "
                f"{response.status_code}: {detail}"
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Convert httpx.HTTPStatusError to GitHubAppError for consistent error handling
            detail = exc.response.text if exc.response else str(exc)
            raise GitHubAppError(
                f"GitHub API request to {path} failed with "
                f"{exc.response.status_code if exc.response else 'unknown'}: {detail}"
            ) from exc
        return response

    def _build_client(self, *, token: str, token_is_app: bool = False) -> httpx.AsyncClient:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "afterquery-app/seed-manager",
            "Authorization": (
                f"Bearer {token}" if token_is_app else f"token {token}"
            ),
        }
        return httpx.AsyncClient(
            base_url=self._settings.api_base_url,
            headers=headers,
            timeout=self._settings.request_timeout_seconds,
        )

    async def _run_git(self, *args: str, cwd: Optional[str] = None) -> str:
        """Execute ``git`` and raise :class:`GitHubAppError` on failure."""

        sanitized_args = [
            "***" if "x-access-token:" in arg else arg for arg in args
        ]
        process = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise GitHubAppError(
                "Git command failed ({}): {}".format(
                    " ".join(sanitized_args), stderr.decode().strip()
                )
            )
        return stdout.decode().strip()

    async def _clone_and_push(
        self,
        *,
        source_url: str,
        source_branch: str,
        destination_url: str,
        destination_branch: str,
    ) -> tuple[str, str]:
        temp_dir = tempfile.mkdtemp(prefix="afterquery-seed-")
        repo_dir = f"{temp_dir}/repo.git"
        branch_sha: Optional[str] = None
        try:
            await self._run_git(
                "clone",
                "--mirror",
                source_url,
                repo_dir,
            )

            # First, try to find the actual default branch in the mirrored repo
            # List all branch refs to see what's available
            try:
                rev_parse_output = await self._run_git(
                    "rev-parse",
                    f"refs/heads/{source_branch}",
                    cwd=repo_dir,
                )
                branch_sha = rev_parse_output.strip() or None
            except GitHubAppError:
                # The specified branch doesn't exist, try to find the default branch from refs
                branch_sha = None
                try:
                    # List all heads to find available branches
                    show_ref_output = await self._run_git(
                        "show-ref",
                        "--heads",
                        cwd=repo_dir,
                    )
                    if show_ref_output.strip():
                        # Get the first branch ref
                        first_ref = show_ref_output.strip().split("\n")[0]
                        if first_ref:
                            # Format: <sha> refs/heads/<branch>
                            parts = first_ref.split()
                            if len(parts) >= 2:
                                branch_sha = parts[0]
                                # Update source_branch to match what we found
                                source_branch = parts[1].replace("refs/heads/", "")
                except GitHubAppError:
                    pass
            
            if branch_sha is None:
                raise GitHubAppError(
                    f"Source repository branch '{source_branch}' not found. "
                    "The repository may be empty or the branch doesn't exist."
                )

            await self._run_git(
                "remote",
                "set-url",
                "--push",
                "origin",
                destination_url,
                cwd=repo_dir,
            )

            await self._run_git(
                "push",
                "--mirror",
                "origin",
                cwd=repo_dir,
            )
            return branch_sha, source_branch
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _ensure_app_jwt(self) -> str:
        now = time.time()
        if self._app_jwt and now < self._app_jwt_expires_at - 30:
            return self._app_jwt

        issued_at = datetime.now(timezone.utc)
        expires_at = issued_at + timedelta(minutes=9)
        payload = {
            "iat": int(issued_at.timestamp()) - 60,
            "exp": int(expires_at.timestamp()),
            "iss": self._settings.app_id,
        }
        token = jwt.encode(payload, self._private_key, algorithm="RS256")
        self._app_jwt = token
        self._app_jwt_expires_at = expires_at.timestamp()
        return token

    async def _create_installation_access_token(
        self,
        *,
        repositories: Sequence[str] | None = None,
        repository_ids: Sequence[int] | None = None,
        permissions: Mapping[str, str] | None = None,
    ) -> tuple[str, datetime]:
        app_jwt = self._ensure_app_jwt()
        async with httpx.AsyncClient(
            base_url=self._settings.api_base_url,
            timeout=self._settings.request_timeout_seconds,
        ) as client:
            payload: dict[str, Any] = {}
            if repositories:
                payload["repositories"] = list(repositories)
            if repository_ids:
                payload["repository_ids"] = list(repository_ids)
            if permissions:
                payload["permissions"] = dict(permissions)
            response = await self._request(
                client,
                "POST",
                f"/app/installations/{self.installation_id}/access_tokens",
                token=app_jwt,
                token_is_app=True,
                json=payload or None,
            )

        data = response.json()
        token = data.get("token")
        expires_at_raw = data.get("expires_at")
        if not isinstance(token, str):
            raise GitHubAppError("GitHub did not return an installation token")
        if not isinstance(expires_at_raw, str):
            raise GitHubAppError("GitHub did not return a token expiration")
        expires_at = datetime.fromisoformat(expires_at_raw.replace("Z", "+00:00"))
        return token, expires_at

    async def _get_cached_installation_token(self) -> str:
        now = time.time()
        if (
            self._installation_token
            and now < self._installation_token_expires_at - 60
        ):
            return self._installation_token

        token, expires_at = await self._create_installation_access_token()
        self._installation_token = token
        self._installation_token_expires_at = expires_at.timestamp()
        return token

    async def ensure_seed_repository(
        self,
        source_repo_url: str,
        *,
        default_branch: str = "main",
    ) -> tuple[GitHubRepository, str, str]:
        """Create a private template repository seeded from ``source_repo_url``."""

        owner, name = _parse_repo_identifier(source_repo_url)
        canonical_source = f"https://github.com/{owner}/{name}"
        slug = _slugify(f"{owner}-{name}")
        repo_name = f"{self._settings.seed_repo_prefix}-{slug}-{uuid.uuid4().hex[:8]}"

        token = await self._get_cached_installation_token()
        async with self._build_client(token=token) as client:
            source_response = await client.get(f"/repos/{owner}/{name}")
            if source_response.status_code == 404:
                raise GitHubAppError("Source repository not found or inaccessible")
            source_response.raise_for_status()
            source_repo = source_response.json()
            source_default_branch = source_repo.get("default_branch") or "main"

        async with self._build_client(token=token) as client:
            response = await client.post(
                f"/orgs/{self.organization}/repos",
                json={
                    "name": repo_name,
                    "private": True,
                    "visibility": "private",
                    "auto_init": False,
                    "description": f"Seed mirror of {canonical_source}",
                },
            )
            if response.status_code not in (201, 202):
                raise GitHubAppError(
                    f"Failed to create seed repository: {response.status_code} {response.text}"
                )

        seed_repo_full_name = f"{self.organization}/{repo_name}"

        # Mirror repository contents using git rather than the deprecated importer API.
        source_clone_url = f"https://x-access-token:{token}@github.com/{owner}/{name}.git"
        destination_clone_url = (
            f"https://x-access-token:{token}@github.com/{seed_repo_full_name}.git"
        )
        # Clone and push, which will return the SHA of the source branch
        # Note: _clone_and_push may adjust source_branch if the requested branch doesn't exist
        branch_sha, actual_source_branch = await self._clone_and_push(
            source_url=source_clone_url,
            source_branch=source_default_branch,
            destination_url=destination_clone_url,
            destination_branch=default_branch,
        )
        
        # If the source branch wasn't what we expected, log it but continue
        if actual_source_branch != source_default_branch:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Source repo default branch was {source_default_branch} but found {actual_source_branch} instead"
            )

        token = await self._get_cached_installation_token()
        async with self._build_client(token=token) as client:
            repo_response = await client.get(f"/repos/{seed_repo_full_name}")
            repo_data = repo_response.json()
            current_default = repo_data.get("default_branch") or default_branch

            if current_default != default_branch:
                rename_response = await client.post(
                    f"/repos/{seed_repo_full_name}/branches/{current_default}/rename",
                    json={"new_name": default_branch},
                )
                if rename_response.status_code not in (200, 201):
                    raise GitHubAppError(
                        "Unable to rename default branch to main: "
                        f"{rename_response.status_code} {rename_response.text}"
                    )

            await client.patch(
                f"/repos/{seed_repo_full_name}",
                json={
                    "is_template": True,
                    "default_branch": default_branch,
                    "private": True,
                },
            )

            try:
                sha = await self._fetch_branch_head_sha(
                    client=client,
                    repo_full_name=seed_repo_full_name,
                    branch=default_branch,
                )
            except GitHubAppError:
                sha = branch_sha

        full_name = repo_data.get("full_name")
        if not isinstance(full_name, str):
            raise GitHubAppError("GitHub did not return the seed repository name")
        repo_id = repo_data.get("id")
        if isinstance(repo_id, str):
            repo_id = int(repo_id)
        if not isinstance(repo_id, int):
            raise GitHubAppError("GitHub did not return the seed repository id")

        return (
            GitHubRepository(
                id=repo_id,
                full_name=full_name,
                html_url=repo_data.get("html_url"),
                default_branch=default_branch,
                clone_url=repo_data.get("clone_url"),
            ),
            sha,
            canonical_source,
        )

    async def refresh_branch_sha(self, repo_full_name: str, branch: str = "main") -> str:
        token = await self._get_cached_installation_token()
        async with self._build_client(token=token) as client:
            return await self._fetch_branch_head_sha(
                client=client,
                repo_full_name=repo_full_name,
                branch=branch,
            )

    async def _fetch_branch_head_sha(
        self,
        *,
        client: httpx.AsyncClient,
        repo_full_name: str,
        branch: str,
        attempts: int = 5,
        initial_delay_seconds: float = 0.5,
    ) -> str:
        """Fetch the head commit SHA for ``branch`` with basic retry logic."""

        delay = initial_delay_seconds
        for attempt in range(attempts):
            response = await client.get(
                f"/repos/{repo_full_name}/git/ref/heads/{branch}"
            )
            if response.status_code == 200:
                data = response.json()
                branch_object = data.get("object", {})
                sha = branch_object.get("sha")
                if isinstance(sha, str):
                    return sha

            if response.status_code == 404:
                branch_response = await client.get(
                    f"/repos/{repo_full_name}/branches/{branch}"
                )
                if branch_response.status_code == 200:
                    branch_data = branch_response.json()
                    commit = branch_data.get("commit", {})
                    sha = commit.get("sha")
                    if isinstance(sha, str):
                        return sha

            if attempt < attempts - 1:
                await asyncio.sleep(delay)
                delay *= 2

        raise GitHubAppError("Unable to determine seed main branch SHA")

    async def create_candidate_repository(
        self,
        seed_repo_full_name: str,
        *,
        default_branch: str,
        candidate_slug: str,
    ) -> GitHubRepository:
        token = await self._get_cached_installation_token()
        seed_owner, seed_name = seed_repo_full_name.split("/", 1)
        repo_name = f"{self._settings.candidate_repo_prefix}-{candidate_slug}-{uuid.uuid4().hex[:6]}"

        async with self._build_client(token=token) as client:
            response = await client.post(
                f"/repos/{seed_owner}/{seed_name}/generate",
                json={
                    "owner": self.organization,
                    "name": repo_name,
                    "private": True,
                    "include_all_branches": False,
                },
            )
            if response.status_code not in (201, 202):
                raise GitHubAppError(
                    "Unable to generate candidate repository: "
                    f"{response.status_code} {response.text}"
                )
            repo_data = response.json()

        full_name = repo_data.get("full_name")
        if not isinstance(full_name, str):
            raise GitHubAppError("GitHub did not return the candidate repository name")
        repo_id = repo_data.get("id")
        if isinstance(repo_id, str):
            repo_id = int(repo_id)
        if not isinstance(repo_id, int):
            raise GitHubAppError("GitHub did not return the candidate repository id")

        return GitHubRepository(
            id=repo_id,
            full_name=full_name,
            html_url=repo_data.get("html_url"),
            default_branch=repo_data.get("default_branch", default_branch),
            clone_url=repo_data.get("clone_url"),
        )

    async def create_repository_access_token(
        self,
        repo_id: int,
        *,
        permissions: Mapping[str, str] | None = None,
    ) -> tuple[str, datetime]:
        permissions = permissions or {"contents": "write", "metadata": "read"}
        return await self._create_installation_access_token(
            repository_ids=[repo_id], permissions=permissions
        )

    async def archive_repository(self, repo_full_name: str) -> None:
        token = await self._get_cached_installation_token()
        async with self._build_client(token=token) as client:
            await client.patch(
                f"/repos/{repo_full_name}", json={"archived": True, "default_branch": "main"}
            )

    async def fetch_installation(self, installation_id: Optional[int] = None) -> dict[str, Any]:
        target_id = installation_id if installation_id is not None else self.installation_id
        app_jwt = self._ensure_app_jwt()
        async with httpx.AsyncClient(
            base_url=self._settings.api_base_url,
            timeout=self._settings.request_timeout_seconds,
        ) as client:
            response = await self._request(
                client,
                "GET",
                f"/app/installations/{target_id}",
                token=app_jwt,
                token_is_app=True,
            )
        return response.json()


@lru_cache
def get_github_app_client() -> GitHubAppClient:
    return GitHubAppClient(get_github_app_settings())

