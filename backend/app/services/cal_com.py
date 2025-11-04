"""Cal.com API integration service."""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import httpx
from dotenv import find_dotenv, load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models

logger = logging.getLogger(__name__)

_DOTENV_PATH = find_dotenv(filename=".env", raise_error_if_not_found=False, usecwd=True)
if _DOTENV_PATH:
    load_dotenv(_DOTENV_PATH)


@dataclass(frozen=True, slots=True)
class CalComSettings:
    """Configuration required to interact with Cal.com API."""

    api_key: str
    api_url: str = "https://api.cal.com/v1"
    api_version: str = "v1"  # v1 or v2
    request_timeout_seconds: float = 10.0


class CalComError(RuntimeError):
    """Raised when a Cal.com API operation fails."""


class CalComService:
    """Service for interacting with Cal.com API."""

    def __init__(self, settings: CalComSettings) -> None:
        self._settings = settings
        self._headers = {
            "Authorization": f"Bearer {self._settings.api_key}",
            "Content-Type": "application/json",
        }
        # Cal.com API v1 uses apiKey as query parameter or header
        self._api_key = settings.api_key

    async def get_user(self) -> dict:
        """Get current Cal.com user information.
        
        Returns the user data, handling nested 'user' key if present.
        """
        async with httpx.AsyncClient(
            base_url=self._settings.api_url,
            timeout=self._settings.request_timeout_seconds,
        ) as client:
            # Try /me endpoint first (v1)
            try:
                response = await client.get(
                    "/me",
                    headers=self._headers,
                    params={"apiKey": self._api_key},
                )
                if response.status_code == 200:
                    user_data = response.json()
                    logger.debug("Cal.com /me API response: %s", user_data)
                    # Cal.com API sometimes returns user data nested under 'user' key
                    if isinstance(user_data, dict) and "user" in user_data:
                        return user_data["user"]
                    return user_data
                else:
                    logger.warning("Cal.com /me returned status %d: %s", response.status_code, response.text)
            except Exception as e:
                logger.warning("Failed to fetch from /me endpoint: %s", e)
            
            # Fallback: try /v2/me if v1 doesn't work
            try:
                v2_url = self._settings.api_url.replace("/v1", "/v2")
                v2_headers = {
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "cal-api-version": "2024-08-13",
                }
                response = await client.get(
                    f"{v2_url}/me",
                    headers=v2_headers,
                )
                if response.status_code == 200:
                    user_data = response.json()
                    logger.debug("Cal.com /v2/me API response: %s", user_data)
                    # Cal.com API sometimes returns user data nested under 'user' key
                    if isinstance(user_data, dict) and "user" in user_data:
                        return user_data["user"]
                    return user_data
                else:
                    logger.warning("Cal.com /v2/me returned status %d: %s", response.status_code, response.text)
            except Exception as e:
                logger.warning("Failed to fetch from /v2/me endpoint: %s", e)
            
            # If both fail, raise error
            raise CalComError("Could not fetch user info from Cal.com API. Please check your API key has the correct permissions.")

    async def get_event_types(self) -> list[dict]:
        """Get list of available event types from Cal.com."""
        async with httpx.AsyncClient(
            base_url=self._settings.api_url,
            timeout=self._settings.request_timeout_seconds,
        ) as client:
            # Cal.com API v1 requires apiKey as a query parameter
            response = await client.get(
                "/event-types",
                headers=self._headers,
                params={"apiKey": self._api_key},
            )

            if response.status_code >= 400:
                detail = response.text
                logger.error("Cal.com failed to get event types: %s", detail)
                raise CalComError(
                    f"Cal.com returned {response.status_code} while fetching event types: {detail}"
                )

            data = response.json()
            logger.debug("Cal.com event-types API response: %s", data)
            
            # Cal.com API returns event types in different formats depending on version
            event_types_list = []
            if isinstance(data, dict):
                # Check for nested event_types array
                if "event_types" in data:
                    event_types_list = data["event_types"]
                # Check if the dict itself represents an event type
                elif "id" in data or "eventTypeId" in data:
                    event_types_list = [data]
                # Check for other possible keys
                elif "data" in data and isinstance(data["data"], list):
                    event_types_list = data["data"]
            elif isinstance(data, list):
                event_types_list = data
            
            logger.info("Extracted %d event type(s) from Cal.com API", len(event_types_list))
            return event_types_list
    
    def generate_booking_link(self, username: str, event_slug: str) -> str:
        """Generate a Cal.com booking link from username and event slug."""
        # Clean the slug
        slug = event_slug.lower().replace(" ", "-").strip("/")
        # Clean the username
        username_clean = username.strip("/").lower()
        return f"https://cal.com/{username_clean}/{slug}"
    
    async def get_event_type_booking_url(self, event_type: dict, username: Optional[str] = None) -> Optional[str]:
        """Get booking URL from event type data.
        
        Cal.com booking URLs follow the format: https://cal.com/{username}/{event-slug}
        """
        # Check if event type has a direct URL field
        if event_type.get("url"):
            url = event_type["url"]
            # Validate it's a cal.com URL
            if url.startswith("https://cal.com/") or url.startswith("http://cal.com/"):
                return url if url.startswith("https://") else url.replace("http://", "https://")
        
        # Check if it has a bookingUrl field
        if event_type.get("bookingUrl"):
            url = event_type["bookingUrl"]
            if url.startswith("https://cal.com/") or url.startswith("http://cal.com/"):
                return url if url.startswith("https://") else url.replace("http://", "https://")
        
        # Try to construct from slug and username (preferred method)
        slug = event_type.get("slug")
        if slug and username:
            return self.generate_booking_link(username, slug)
        
        return None

    async def create_booking(
        self,
        event_type_id: str,
        email: str,
        name: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        timezone: str = "UTC",
        responses: Optional[dict] = None,
    ) -> dict:
        """Create a new booking in Cal.com.
        
        If start_time is not provided, Cal.com will return a booking link
        that allows the candidate to choose their own time.
        """
        payload = {
            "eventTypeId": int(event_type_id) if event_type_id.isdigit() else event_type_id,
            "responses": {
                "email": email,
                "name": name,
                "language": "en",  # Required by Cal.com API
                "metadata": {},  # Required by Cal.com API
                **(responses or {}),
            },
            "timeZone": timezone,
            "language": "en",  # Required by Cal.com API
            "metadata": {},  # Required by Cal.com API
        }
        
        # Only include start/end times if provided
        # If not provided, Cal.com will create a booking link instead
        if start_time:
            payload["start"] = start_time
        if end_time:
            payload["end"] = end_time

        async with httpx.AsyncClient(
            base_url=self._settings.api_url,
            timeout=self._settings.request_timeout_seconds,
        ) as client:
            # Cal.com API v1 requires apiKey as a query parameter
            response = await client.post(
                "/bookings",
                json=payload,
                headers=self._headers,
                params={"apiKey": self._api_key},
            )

            if response.status_code >= 400:
                detail = response.text
                logger.error("Cal.com failed to create booking: %s", detail)
                raise CalComError(
                    f"Cal.com returned {response.status_code} while creating booking: {detail}"
                )

            return response.json()

    async def get_booking(self, booking_id: str) -> dict:
        """Get booking details from Cal.com.
        
        Returns the booking data, handling nested 'booking' key if present.
        """
        async with httpx.AsyncClient(
            base_url=self._settings.api_url,
            timeout=self._settings.request_timeout_seconds,
        ) as client:
            # Cal.com API v1 requires apiKey as a query parameter
            response = await client.get(
                f"/bookings/{booking_id}",
                headers=self._headers,
                params={"apiKey": self._api_key},
            )

            if response.status_code >= 400:
                detail = response.text
                logger.error("Cal.com failed to get booking: %s", detail)
                raise CalComError(
                    f"Cal.com returned {response.status_code} while fetching booking: {detail}"
                )

            data = response.json()
            # Cal.com API sometimes returns booking data nested under 'booking' key
            if isinstance(data, dict) and "booking" in data:
                return data["booking"]
            return data
    
    async def list_bookings(
        self,
        limit: int = 100,
        cursor: Optional[int] = None,
        filters: Optional[dict] = None,
    ) -> dict:
        """List all bookings from Cal.com.
        
        Returns a dict with 'bookings' list and pagination info.
        """
        async with httpx.AsyncClient(
            base_url=self._settings.api_url,
            timeout=self._settings.request_timeout_seconds,
        ) as client:
            params = {
                "apiKey": self._api_key,
                "limit": limit,
            }
            if cursor:
                params["cursor"] = cursor
            
            # Add any filter parameters
            if filters:
                params.update(filters)
            
            response = await client.get(
                "/bookings",
                headers=self._headers,
                params=params,
            )

            if response.status_code >= 400:
                detail = response.text
                logger.error("Cal.com failed to list bookings: %s", detail)
                raise CalComError(
                    f"Cal.com returned {response.status_code} while listing bookings: {detail}"
                )

            data = response.json()
            # Handle different response formats
            if isinstance(data, dict):
                # If it's already a dict with bookings, return as-is
                if "bookings" in data or "data" in data:
                    return data
                # If it's a list wrapped in a dict, extract it
                if "bookings" not in data and isinstance(data.get("data"), list):
                    return {"bookings": data["data"]}
            elif isinstance(data, list):
                # If response is a direct list, wrap it
                return {"bookings": data}
            
            return data

    async def cancel_booking(self, booking_id: str, reason: Optional[str] = None) -> dict:
        """Cancel a booking in Cal.com."""
        # Prepare params - Cal.com may accept reason as query parameter
        params = {"apiKey": self._api_key}
        if reason:
            params["reason"] = reason

        async with httpx.AsyncClient(
            base_url=self._settings.api_url,
            timeout=self._settings.request_timeout_seconds,
        ) as client:
            # Cal.com API v1 requires apiKey as a query parameter
            # For DELETE requests, we pass params instead of json body
            response = await client.delete(
                f"/bookings/{booking_id}",
                headers=self._headers,
                params=params,
            )

            if response.status_code >= 400:
                detail = response.text
                logger.error("Cal.com failed to cancel booking: %s", detail)
                raise CalComError(
                    f"Cal.com returned {response.status_code} while canceling booking: {detail}"
                )

            if response.status_code == 204:
                return {"success": True}
            
            # Try to parse JSON response if available
            try:
                return response.json()
            except Exception:
                return {"success": True}


async def get_cal_com_settings(
    session: AsyncSession, org_id: Optional[uuid.UUID] = None
) -> Optional[CalComSettings]:
    """Get Cal.com settings from database or environment."""
    # Try to get from database first
    if org_id:
        try:
            result = await session.execute(
                select(models.CalComConfig).where(models.CalComConfig.org_id == org_id)
            )
            config = result.scalar_one_or_none()
            if config:
                return CalComSettings(
                    api_key=config.api_key,
                    api_url=config.api_url,
                    api_version="v1",
                )
        except Exception as e:
            logger.warning("Failed to load Cal.com config from database: %s", e)

    # Fallback to environment variable
    api_key = os.getenv("CAL_COM_API_KEY")
    if api_key:
        api_url = os.getenv("CAL_COM_API_URL", "https://api.cal.com/v1")
        api_version = os.getenv("CAL_COM_API_VERSION", "v1")
        return CalComSettings(api_key=api_key, api_url=api_url, api_version=api_version)

    return None


@lru_cache
def get_cal_com_service_from_env() -> Optional[CalComService]:
    """Get Cal.com service from environment variables (for fallback)."""
    api_key = os.getenv("CAL_COM_API_KEY")
    if not api_key:
        return None
    api_url = os.getenv("CAL_COM_API_URL", "https://api.cal.com/v1")
    settings = CalComSettings(api_key=api_key, api_url=api_url)
    return CalComService(settings)

