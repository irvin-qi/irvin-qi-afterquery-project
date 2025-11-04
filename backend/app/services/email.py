"""Email sending helpers backed by Resend."""

from __future__ import annotations

import html
import uuid
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Mapping, Optional, Sequence

import httpx
from dotenv import find_dotenv, load_dotenv
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models

logger = logging.getLogger(__name__)

_DOTENV_PATH = find_dotenv(filename=".env", raise_error_if_not_found=False, usecwd=True)
if _DOTENV_PATH:
    load_dotenv(_DOTENV_PATH)


@dataclass(frozen=True, slots=True)
class ResendSettings:
    """Configuration required to send transactional email via Resend."""

    api_key: str
    from_email: str
    candidate_app_url: str
    from_name: Optional[str] = None
    reply_to_email: Optional[str] = None
    api_base_url: str = "https://api.resend.com"
    request_timeout_seconds: float = 10.0

    @property
    def normalized_candidate_base(self) -> str:
        return self.candidate_app_url.rstrip("/")


_REQUIRED_ENVIRONMENT_KEYS: Mapping[str, Sequence[str]] = {
    "api_key": ("RESEND_API_KEY",),  # Required if using Resend
    "from_email": ("RESEND_FROM_EMAIL",),
    "candidate_app_url": ("CANDIDATE_APP_URL", "NEXT_PUBLIC_CANDIDATE_APP_URL"),
}

_OPTIONAL_ENVIRONMENT_KEYS: Mapping[str, Sequence[str]] = {
    "from_name": ("RESEND_FROM_NAME",),
    "reply_to_email": ("RESEND_REPLY_TO_EMAIL",),
    "api_base_url": ("RESEND_API_BASE_URL",),
    "request_timeout_seconds": ("RESEND_HTTP_TIMEOUT_SECONDS",),
}


CANDIDATE_ASSESSMENT_STARTED_TEMPLATE_KEY = "candidate_assessment_started"
CANDIDATE_ASSESSMENT_SUBMITTED_TEMPLATE_KEY = "candidate_submission_received"


_STATUS_TEMPLATE_CONFIG: dict[models.EmailEventType, dict[str, str]] = {
    models.EmailEventType.assessment_started: {
        "key": CANDIDATE_ASSESSMENT_STARTED_TEMPLATE_KEY,
        "default_subject": "Your assessment is underway",
        "default_body": (
            "Hi {candidate_name}, we're excited to see your progress on {assessment_title}.\n\n"
            "You can keep working in your project repository: {candidate_repo_url}.\n"
            "Remember to submit before {complete_deadline}."
        ),
    },
    models.EmailEventType.submission_received: {
        "key": CANDIDATE_ASSESSMENT_SUBMITTED_TEMPLATE_KEY,
        "default_subject": "Thanks for submitting {assessment_title}",
        "default_body": (
            "Hi {candidate_name}, thanks for submitting {assessment_title}.\n\n"
            "We'll review your work and follow up soon."
        ),
    },
}


def _read_first_env(names: Sequence[str]) -> Optional[str]:
    for env_name in names:
        value = os.getenv(env_name)
        if value is not None and value.strip() != "":
            return value
    return None


def _build_missing_env_message(missing: list[str]) -> str:
    detail = "Resend environment variables are not configured"
    if missing:
        detail = f"{detail}: missing {', '.join(missing)}"
    return detail


@lru_cache
def get_resend_settings() -> ResendSettings:
    """Get Resend settings. Supports Mailtrap as an easier alternative (no DNS required)."""
    values: dict[str, str] = {}
    missing: list[str] = []
    
    # Check if using Mailtrap (easier, no DNS verification needed)
    mailtrap_token = _read_first_env(("MAILTRAP_API_TOKEN",))
    using_mailtrap = mailtrap_token is not None

    for field_name, env_names in _REQUIRED_ENVIRONMENT_KEYS.items():
        # Skip api_key requirement if using Mailtrap
        if field_name == "api_key" and using_mailtrap:
            values[field_name] = "mailtrap-placeholder"
            continue
            
        value = _read_first_env(env_names)
        if value is None:
            missing.append(" or ".join(env_names))
            continue
        values[field_name] = value

    if missing:
        raise RuntimeError(_build_missing_env_message(missing))

    for field_name, env_names in _OPTIONAL_ENVIRONMENT_KEYS.items():
        value = _read_first_env(env_names)
        if value is not None:
            values[field_name] = value

    api_base_url = values.get("api_base_url", "https://api.resend.com")

    timeout_value = values.get("request_timeout_seconds")
    request_timeout = 10.0
    if timeout_value is not None:
        try:
            request_timeout = float(timeout_value)
        except ValueError as exc:  # pragma: no cover - configuration error
            raise RuntimeError(
                "Resend environment variables are not configured:"
                " RESEND_HTTP_TIMEOUT_SECONDS must be a number"
            ) from exc

    return ResendSettings(
        api_key=values["api_key"],
        from_email=values["from_email"],
        candidate_app_url=values["candidate_app_url"],
        from_name=values.get("from_name"),
        reply_to_email=values.get("reply_to_email"),
        api_base_url=api_base_url,
        request_timeout_seconds=request_timeout,
    )


class EmailServiceError(RuntimeError):
    """Raised when an email could not be delivered."""


@dataclass(slots=True)
class InvitationEmailPayload:
    invitation: models.Invitation
    assessment: models.Assessment
    start_link_token: str


class ResendEmailService:
    """Send candidate emails through Resend."""

    def __init__(self, settings: ResendSettings) -> None:
        self._settings = settings
        self._candidate_status_event_types_supported: Optional[bool] = None
        self._candidate_status_constraint_warning_logged = False

    def _build_from_header(self) -> str:
        if self._settings.from_name:
            return f"{self._settings.from_name} <{self._settings.from_email}>"
        return self._settings.from_email

    def _build_start_link(self, token: str) -> str:
        base = self._settings.normalized_candidate_base
        return f"{base}/candidates/{token}"

    @staticmethod
    def _format_deadline(value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M %Z")

    def _build_base_context(
        self,
        invitation: models.Invitation,
        assessment: models.Assessment,
        *,
        start_link: Optional[str] = None,
    ) -> dict[str, str]:
        context: dict[str, str] = {
            "candidate_name": invitation.candidate_name or invitation.candidate_email,
            "candidate_email": invitation.candidate_email,
            "assessment_title": assessment.title,
        }
        if start_link:
            context["start_link"] = start_link

        optional_context = {
            "start_deadline": self._format_deadline(invitation.start_deadline),
            "complete_deadline": self._format_deadline(invitation.complete_deadline),
            "started_at": self._format_deadline(invitation.started_at),
            "submitted_at": self._format_deadline(invitation.submitted_at),
        }
        for key, value in optional_context.items():
            if value:
                context[key] = value

        return context

    def _render_template(
        self,
        template: Optional[str],
        context: Mapping[str, str],
        *,
        default: str,
        include_start_link_fallback: bool = False,
    ) -> str:
        if not template:
            template = default
        rendered = template
        for key, value in context.items():
            for placeholder in (f"{{{{{key}}}}}", f"{{{key}}}"):
                rendered = rendered.replace(placeholder, value)
        if include_start_link_fallback and "{{start_link}}" not in template and context.get("start_link"):
            rendered = f"{rendered}\n\nStart your project: {context['start_link']}"
        return rendered

    def _build_email_content(
        self, payload: InvitationEmailPayload
    ) -> tuple[str, str, str]:
        invitation = payload.invitation
        assessment = payload.assessment
        start_link = self._build_start_link(payload.start_link_token)

        subject_default = "Your coding interview project is ready"
        body_default = (
            "Hi {{candidate_name}},\n\n"
            "Your project for {{assessment_title}} is ready. "
            "Use the link below to get started and remember to submit before the deadline.\n\n"
            "{{start_link}}\n"
        )

        context = self._build_base_context(
            invitation, assessment, start_link=start_link
        )

        subject_template = assessment.candidate_email_subject
        subject = self._render_template(
            subject_template, context, default=subject_default, include_start_link_fallback=False
        )

        body_template = assessment.candidate_email_body
        text_body = self._render_template(
            body_template,
            context,
            default=body_default,
            include_start_link_fallback=True,
        )

        html_body = "<br>".join(html.escape(part) for part in text_body.split("\n"))
        return subject.strip(), text_body.strip(), html_body

    async def _send_email(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str,
        *,
        context_label: str,
    ) -> dict:
        # Check if using Mailtrap (easier alternative, no DNS verification needed)
        mailtrap_token = os.getenv("MAILTRAP_API_TOKEN")
        if mailtrap_token:
            return await self._send_via_mailtrap(
                to_email, subject, text_body, html_body, context_label, mailtrap_token
            )
        
        # Use Resend API
        headers = {
            "Authorization": f"Bearer {self._settings.api_key}",
            "Content-Type": "application/json",
        }
        
        from_header = self._build_from_header()
        logger.debug("Sending email with 'from' header: %s", from_header)
        
        json_payload: dict[str, object] = {
            "from": from_header,
            "to": [to_email],
            "subject": subject,
            "text": text_body,
            "html": html_body,
        }
        if self._settings.reply_to_email:
            json_payload["reply_to"] = [self._settings.reply_to_email]

        async with httpx.AsyncClient(
            base_url=self._settings.api_base_url,
            timeout=self._settings.request_timeout_seconds,
        ) as client:
            response = await client.post("/emails", json=json_payload, headers=headers)

        if response.status_code >= 400:
            detail = response.text
            logger.error("Resend failed to send %s email: %s", context_label, detail)
            logger.error("Request payload 'from' field was: %s", from_header)
            raise EmailServiceError(
                f"Resend returned {response.status_code} while sending {context_label} email: {detail}"
            )

        return response.json()
    
    async def _send_via_mailtrap(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str,
        context_label: str,
        api_token: str,
    ) -> dict:
        """Send email via Mailtrap Email Testing API - no DNS verification needed!"""
        mailtrap_inbox_id = os.getenv("MAILTRAP_INBOX_ID", "")
        if not mailtrap_inbox_id:
            raise EmailServiceError("MAILTRAP_INBOX_ID environment variable is required when using Mailtrap")
        
        api_base_url = "https://sandbox.api.mailtrap.io"
        url = f"{api_base_url}/api/send/{mailtrap_inbox_id}"
        
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }
        
        # Mailtrap API format
        json_payload: dict[str, object] = {
            "from": {
                "email": self._settings.from_email,
                "name": self._settings.from_name or "Afterquery",
            },
            "to": [{"email": to_email}],
            "subject": subject,
            "text": text_body,
            "html": html_body,
        }
        
        logger.info("Sending email via Mailtrap to %s (inbox: %s)", to_email, mailtrap_inbox_id)
        
        async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
            response = await client.post(url, json=json_payload, headers=headers)
        
        logger.info("Mailtrap API response: status=%s", response.status_code)
        
        if response.status_code >= 400:
            detail = response.text
            logger.error("Mailtrap failed to send %s email: %s", context_label, detail)
            logger.error("Request URL: %s", url)
            logger.error("Request payload: %s", json_payload)
            raise EmailServiceError(
                f"Mailtrap returned {response.status_code} while sending {context_label} email: {detail}"
            )
        
        result = response.json()
        logger.info("✅ Email sent via Mailtrap (testing mode) - check your Mailtrap inbox at https://mailtrap.io/inboxes/%s/messages", mailtrap_inbox_id)
        return result

    async def send_invitation_email(
        self,
        session: AsyncSession,
        payload: InvitationEmailPayload,
    ) -> None:
        subject, text_body, html_body = self._build_email_content(payload)
        invitation = payload.invitation

        data = await self._send_email(
            invitation.candidate_email,
            subject,
            text_body,
            html_body,
            context_label="invitation",
        )
        provider_id = str(data.get("id")) if data.get("id") is not None else None

        invitation.sent_at = datetime.now(timezone.utc)

        await self._record_email_event(
            session,
            invitation_id=invitation.id,
            event_type=models.EmailEventType.invite,
            provider_id=provider_id,
            to_email=invitation.candidate_email,
            status=data.get("status") if isinstance(data.get("status"), str) else "sent",
        )

    async def send_candidate_status_email(
        self,
        session: AsyncSession,
        *,
        invitation: models.Invitation,
        assessment: models.Assessment,
        event_type: models.EmailEventType,
        extra_context: Optional[Mapping[str, Optional[str]]] = None,
    ) -> bool:
        config = _STATUS_TEMPLATE_CONFIG.get(event_type)
        if config is None:
            raise ValueError(f"Unsupported email event type: {event_type}")

        result = await session.execute(
            select(models.EmailTemplate)
            .where(models.EmailTemplate.org_id == assessment.org_id)
            .where(models.EmailTemplate.key == config["key"])
        )
        template = result.scalar_one_or_none()
        if template is None:
            logger.debug("Skipping %s email; no template configured", event_type.value)
            return False

        context = self._build_base_context(invitation, assessment)
        if extra_context:
            for key, value in extra_context.items():
                if value:
                    context[key] = value

        subject_template = (template.subject or "").strip() or config["default_subject"]
        body_template = (template.body or "").strip() or config["default_body"]

        subject = self._render_template(
            subject_template, context, default=config["default_subject"], include_start_link_fallback=False
        )
        text_body = self._render_template(
            body_template, context, default=config["default_body"], include_start_link_fallback=False
        )
        html_body = "<br>".join(html.escape(part) for part in text_body.split("\n"))

        data = await self._send_email(
            invitation.candidate_email,
            subject.strip(),
            text_body.strip(),
            html_body,
            context_label=event_type.value,
        )
        provider_id = str(data.get("id")) if data.get("id") is not None else None

        await self._record_email_event(
            session,
            invitation_id=invitation.id,
            event_type=event_type,
            provider_id=provider_id,
            to_email=invitation.candidate_email,
            status=data.get("status") if isinstance(data.get("status"), str) else "sent",
        )
        return True

    async def _record_email_event(
        self,
        session: AsyncSession,
        *,
        invitation_id: uuid.UUID,
        event_type: models.EmailEventType,
        provider_id: Optional[str],
        to_email: str,
        status: str,
    ) -> None:
        stored_type = await self._resolve_email_event_type(session, event_type)
        email_event = models.EmailEvent(
            invitation_id=invitation_id,
            type=stored_type,
            provider_id=provider_id,
            to_email=to_email,
            status=status,
        )
        session.add(email_event)
        await session.flush()

    async def _resolve_email_event_type(
        self, session: AsyncSession, event_type: models.EmailEventType
    ) -> Optional[models.EmailEventType]:
        if event_type not in _STATUS_TEMPLATE_CONFIG:
            return event_type
        if await self._supports_candidate_status_event_types(session):
            return event_type
        if not self._candidate_status_constraint_warning_logged:
            logger.warning(
                "email_events.type check constraint is missing candidate status values; "
                "storing %s email events without a type. "
                "Run `ALTER TABLE email_events DROP CONSTRAINT email_events_type_check; "
                "ALTER TABLE email_events ADD CONSTRAINT email_events_type_check CHECK "
                "(type IN ('invite','reminder','follow_up','assessment_started','submission_received'));`",
                event_type.value,
            )
            self._candidate_status_constraint_warning_logged = True
        return None

    async def _supports_candidate_status_event_types(self, session: AsyncSession) -> bool:
        if self._candidate_status_event_types_supported is not None:
            return self._candidate_status_event_types_supported

        constraint_def: Optional[str] = None
        try:
            result = await session.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) AS definition "
                    "FROM pg_constraint WHERE conname = 'email_events_type_check'"
                )
            )
            constraint_def = result.scalar_one_or_none()
        except SQLAlchemyError:
            logger.exception(
                "Failed to inspect email_events_type_check constraint; assuming candidate status "
                "email event types are unsupported"
            )

        supported = False
        if constraint_def:
            required_tokens = ("'assessment_started'", "'submission_received'")
            supported = all(token in constraint_def for token in required_tokens)

        self._candidate_status_event_types_supported = supported
        return supported


@lru_cache
def get_resend_email_service() -> ResendEmailService:
    return ResendEmailService(get_resend_settings())
