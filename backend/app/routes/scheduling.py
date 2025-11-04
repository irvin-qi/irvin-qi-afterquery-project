"""Scheduling endpoints for Cal.com integration."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import models, schemas, utils
from ..auth import SupabaseSession, require_roles
from ..database import get_session
from ..services.cal_com import CalComError, CalComService, get_cal_com_settings
from ..services.email import (
    ResendEmailService,
    get_resend_email_service,
)

router = APIRouter(prefix="/api/admin/scheduling", tags=["scheduling"])

logger = logging.getLogger(__name__)


async def _get_cal_com_service(
    session: AsyncSession,
    org_id: Optional[uuid.UUID] = None,
) -> CalComService:
    """Get Cal.com service, raising error if not configured."""
    settings = await get_cal_com_settings(session, str(org_id) if org_id else None)
    if not settings:
        raise HTTPException(
            status_code=400,
            detail="Cal.com API key not configured. Please set CAL_COM_API_KEY environment variable or configure in settings.",
        )
    return CalComService(settings)


@router.get("/candidates", response_model=list[schemas.SchedulingAssessment])
async def get_scheduling_candidates(
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "admin", "service_role")),
) -> list[schemas.SchedulingAssessment]:
    """Get candidates grouped by assessment for scheduling."""
    # Get org for current user
    membership_query = (
        select(models.OrgMember)
        .where(models.OrgMember.supabase_user_id == current_session.user.id)
        .order_by(models.OrgMember.created_at)
    )
    membership_result = await session.execute(membership_query)
    membership = membership_result.scalar_one_or_none()
    
    if not membership:
        raise HTTPException(status_code=403, detail="No organization membership found")

    org_id = membership.org_id

    # Get all assessments for this org
    assessments_result = await session.execute(
        select(models.Assessment)
        .where(models.Assessment.org_id == org_id)
        .options(selectinload(models.Assessment.invitations))
        .order_by(models.Assessment.created_at.desc())
    )
    assessments = assessments_result.scalars().all()

    # Get all bookings for invitations
    invitations_result = await session.execute(
        select(models.Invitation)
        .where(models.Invitation.assessment_id.in_([a.id for a in assessments]))
        .options(selectinload(models.Invitation.cal_com_bookings))
    )
    all_invitations = invitations_result.scalars().all()

    # Create a mapping of invitation_id to latest booking
    booking_map: dict[uuid.UUID, models.CalComBooking] = {}
    for invitation in all_invitations:
        if invitation.cal_com_bookings:
            # Get the most recent booking
            latest_booking = max(
                invitation.cal_com_bookings,
                key=lambda b: b.created_at or datetime.min.replace(tzinfo=timezone.utc),
            )
            booking_map[invitation.id] = latest_booking

    # Group candidates by assessment
    result: list[schemas.SchedulingAssessment] = []
    for assessment in assessments:
        # Filter to submitted invitations (top candidates)
        candidates = []
        for invitation in assessment.invitations:
            if invitation.status == models.InvitationStatus.submitted:
                booking = booking_map.get(invitation.id)
                booking_schema = None
                if booking:
                    booking_schema = schemas.CalComBookingResponse(
                        id=str(booking.id),
                        invitation_id=str(booking.invitation_id) if booking.invitation_id else None,
                        booking_id=booking.booking_id,
                        event_type_id=booking.event_type_id,
                        booking_url=booking.booking_url,
                        start_time=booking.start_time.isoformat() if booking.start_time else None,
                        end_time=booking.end_time.isoformat() if booking.end_time else None,
                        status=booking.status,
                        title=booking.title,
                        description=booking.description,
                        created_at=booking.created_at.isoformat(),
                    )

                candidates.append(
                    schemas.SchedulingCandidate(
                        invitation_id=str(invitation.id),
                        candidate_email=invitation.candidate_email,
                        candidate_name=invitation.candidate_name or invitation.candidate_email,
                        assessment_id=str(assessment.id),
                        assessment_title=assessment.title,
                        status=invitation.status.value,
                        submitted_at=invitation.submitted_at.isoformat() if invitation.submitted_at else None,
                        booking=booking_schema,
                    )
                )

        # Sort by submitted_at (most recent first)
        candidates.sort(
            key=lambda c: c.submitted_at or "",
            reverse=True,
        )

        if candidates:  # Only include assessments with submitted candidates
            result.append(
                schemas.SchedulingAssessment(
                    assessment_id=str(assessment.id),
                    assessment_title=assessment.title,
                    candidates=candidates,
                )
            )

    return result


@router.get("/cal-com/event-types", response_model=list[schemas.CalComEventType])
async def get_cal_com_event_types(
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "admin", "service_role")),
) -> list[schemas.CalComEventType]:
    """Get available Cal.com event types."""
    # Get org for current user
    membership_query = (
        select(models.OrgMember)
        .where(models.OrgMember.supabase_user_id == current_session.user.id)
        .order_by(models.OrgMember.created_at)
    )
    membership_result = await session.execute(membership_query)
    membership = membership_result.scalar_one_or_none()
    
    if not membership:
        raise HTTPException(status_code=403, detail="No organization membership found")

    org_id = membership.org_id

    try:
        cal_com_service = await _get_cal_com_service(session, org_id=org_id)
    except HTTPException:
        # Re-raise HTTPException (e.g., API key not configured)
        raise
    
    try:
        event_types = await cal_com_service.get_event_types()
    except CalComError as e:
        logger.error("Failed to fetch Cal.com event types: %s", e)
        # Return empty list instead of 500 error - frontend will handle gracefully
        return []

    # Transform to schema
    result = []
    for et in event_types:
        result.append(
            schemas.CalComEventType(
                id=str(et.get("id", "")),
                title=et.get("title", ""),
                slug=et.get("slug"),
                description=et.get("description"),
                length=et.get("length"),
                hidden=et.get("hidden", False),
            )
        )

    return result


@router.post("/cal-com/bookings", response_model=schemas.CalComBookingResponse)
async def create_cal_com_booking(
    payload: schemas.CalComBookingCreate,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "admin", "service_role")),
) -> schemas.CalComBookingResponse:
    """Create a Cal.com booking for a candidate."""
    # Get org for current user
    membership_query = (
        select(models.OrgMember)
        .where(models.OrgMember.supabase_user_id == current_session.user.id)
        .order_by(models.OrgMember.created_at)
    )
    membership_result = await session.execute(membership_query)
    membership = membership_result.scalar_one_or_none()
    
    if not membership:
        raise HTTPException(status_code=403, detail="No organization membership found")

    org_id = membership.org_id

    # Get invitation
    try:
        invitation_id = uuid.UUID(payload.invitation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid invitation ID")

    # Load invitation with assessment - we need to check org_id
    # But we'll extract the org_id immediately to avoid lazy loading later
    invitation_result = await session.execute(
        select(models.Invitation)
        .where(models.Invitation.id == invitation_id)
        .options(selectinload(models.Invitation.assessment))
    )
    invitation = invitation_result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")

    # Verify invitation belongs to user's org
    if invitation.assessment.org_id != org_id:
        raise HTTPException(status_code=403, detail="Invitation does not belong to your organization")

    try:
        cal_com_service = await _get_cal_com_service(session, org_id=org_id)
    except HTTPException:
        # Re-raise HTTPException (e.g., API key not configured)
        raise

    # Generate booking link from event type instead of creating actual booking
    # This allows candidates to choose their own time
    try:
        # Get event types to find the slug and URL
        event_types = await cal_com_service.get_event_types()
        event_type = None
        for et in event_types:
            if str(et.get("id")) == str(payload.event_type_id):
                event_type = et
                break
        
        if not event_type:
            raise HTTPException(status_code=404, detail="Event type not found")
        
        logger.info("Event type data: %s", event_type)
        
        # Get user info first to get username (REQUIRED for booking links)
        username = None
        try:
            user_info = await cal_com_service.get_user()
            logger.info("User info: %s", user_info)
            
            # Try multiple fields to get username (Cal.com uses different field names)
            username = (
                user_info.get("username")
                or user_info.get("name")
                or user_info.get("slug")  # Some APIs use slug
                or (user_info.get("email", "").split("@")[0] if user_info.get("email") else None)
            )
            
            if not username:
                logger.warning("Could not extract username from user info: %s", user_info)
        except CalComError as e:
            logger.error("Could not fetch user info: %s", e)
        
        if not username:
            raise HTTPException(
                status_code=500,
                detail="Could not retrieve Cal.com username. Please ensure your API key has access to user information and your Cal.com account has a username configured in Settings > Profile."
            )
        
        # Try multiple methods to get the booking URL (in order of preference)
        booking_url = None
        
        # Method 1: Check if event type has a direct URL field (most reliable)
        if event_type.get("url"):
            url = event_type["url"]
            if url.startswith("https://cal.com/") or url.startswith("http://cal.com/"):
                booking_url = url if url.startswith("https://") else url.replace("http://", "https://")
                logger.info("Using URL from event type: %s", booking_url)
        elif event_type.get("bookingUrl"):
            url = event_type["bookingUrl"]
            if url.startswith("https://cal.com/") or url.startswith("http://cal.com/"):
                booking_url = url if url.startswith("https://") else url.replace("http://", "https://")
                logger.info("Using bookingUrl from event type: %s", booking_url)
        
        # Method 2: Construct from username + slug (standard format)
        if not booking_url and event_type.get("slug"):
            booking_url = cal_com_service.generate_booking_link(username, event_type["slug"])
            logger.info("Constructed URL from username + slug: %s (username: %s, slug: %s)", booking_url, username, event_type["slug"])
        
        # Method 3: Try to construct from title if slug not available (fallback)
        if not booking_url and event_type.get("title"):
            # Create slug from title
            event_slug = (
                event_type.get("title", "")
                .lower()
                .replace(" ", "-")
                .replace("'", "")
                .replace(",", "")
                .replace(".", "")
                .replace(":", "")
                .replace("(", "")
                .replace(")", "")
                .replace("/", "-")
                .replace("--", "-")
                .strip("-")
            )
            booking_url = cal_com_service.generate_booking_link(username, event_slug)
            logger.info("Constructed URL from username + title: %s (username: %s, slug: %s)", booking_url, username, event_slug)
        
        # Final validation - ensure we have a valid booking URL
        if not booking_url:
            error_msg = (
                f"Could not generate booking URL. "
                f"Event type: {event_type.get('title')}, "
                f"Username: {username}, "
                f"Slug: {event_type.get('slug')}, "
                f"Event type data: {event_type}"
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=500,
                detail="Could not generate booking URL. Please ensure your Cal.com event type has a slug configured and your API key has access to user information."
            )
        
        # Ensure URL is valid
        if not booking_url.startswith("https://cal.com/"):
            error_msg = f"Generated invalid booking URL: {booking_url}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)
        
        # Create a unique booking ID for tracking
        booking_id = f"link-{invitation_id}-{payload.event_type_id}-{uuid.uuid4().hex[:8]}"
        
    except HTTPException:
        raise
    except CalComError as e:
        logger.error("Failed to generate Cal.com booking link: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error generating booking link")
        raise HTTPException(status_code=500, detail=f"Failed to generate booking link: {str(e)}")

    # Check if a booking link already exists for this invitation and event type
    # Note: We don't need to eager load relationships since we only access scalar fields
    existing_booking_result = await session.execute(
        select(models.CalComBooking)
        .where(models.CalComBooking.invitation_id == invitation_id)
        .where(models.CalComBooking.event_type_id == payload.event_type_id)
        .order_by(models.CalComBooking.created_at.desc())
    )
    existing_booking = existing_booking_result.scalar_one_or_none()

    if existing_booking:
        # Update existing booking with new URL (in case event type URL changed)
        existing_booking.booking_url = booking_url
        existing_booking.title = event_type.get("title") if event_type else existing_booking.title
        existing_booking.description = event_type.get("description") if event_type else existing_booking.description
        await session.commit()
        await session.refresh(existing_booking)
        booking = existing_booking
    else:
        # Create new booking link
        booking = models.CalComBooking(
            invitation_id=invitation_id,
            booking_id=booking_id,
            event_type_id=payload.event_type_id,
            booking_url=booking_url,
            start_time=None,  # No specific time - candidate chooses
            end_time=None,
            status="pending",  # Pending until candidate books
            title=event_type.get("title") if event_type else None,
            description=event_type.get("description") if event_type else None,
        )
        session.add(booking)
        await session.commit()
        await session.refresh(booking)

    # Extract all data before returning to avoid lazy loading issues
    # This ensures we don't access relationships after the session might be closed
    response_data = schemas.CalComBookingResponse(
        id=str(booking.id),
        invitation_id=str(booking.invitation_id) if booking.invitation_id else None,
        booking_id=booking.booking_id,
        event_type_id=booking.event_type_id,
        booking_url=booking.booking_url,
        start_time=booking.start_time.isoformat() if booking.start_time else None,
        end_time=booking.end_time.isoformat() if booking.end_time else None,
        status=booking.status,
        title=booking.title,
        description=booking.description,
        created_at=booking.created_at.isoformat(),
    )
    
    return response_data


@router.get("/cal-com/bookings", response_model=list[schemas.CalComBookingResponse])
async def get_cal_com_bookings(
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "admin", "service_role")),
) -> list[schemas.CalComBookingResponse]:
    """Get all Cal.com bookings for the current organization."""
    # Get org for current user
    membership_query = (
        select(models.OrgMember)
        .where(models.OrgMember.supabase_user_id == current_session.user.id)
        .order_by(models.OrgMember.created_at)
    )
    membership_result = await session.execute(membership_query)
    membership = membership_result.scalar_one_or_none()
    
    if not membership:
        raise HTTPException(status_code=403, detail="No organization membership found")

    org_id = membership.org_id

    # Get all bookings for invitations in this org
    bookings_result = await session.execute(
        select(models.CalComBooking)
        .join(models.Invitation)
        .join(models.Assessment)
        .where(models.Assessment.org_id == org_id)
        .order_by(models.CalComBooking.start_time.desc().nullslast())
    )
    bookings = bookings_result.scalars().all()

    return [
        schemas.CalComBookingResponse(
            id=str(booking.id),
            invitation_id=str(booking.invitation_id) if booking.invitation_id else None,
            booking_id=booking.booking_id,
            event_type_id=booking.event_type_id,
            booking_url=booking.booking_url,
            start_time=booking.start_time.isoformat() if booking.start_time else None,
            end_time=booking.end_time.isoformat() if booking.end_time else None,
            status=booking.status,
            title=booking.title,
            description=booking.description,
            created_at=booking.created_at.isoformat(),
        )
        for booking in bookings
    ]


@router.post("/send-emails")
async def send_scheduling_emails(
    payload: schemas.SendSchedulingEmailRequest,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "admin", "service_role")),
    email_service: ResendEmailService = Depends(get_resend_email_service),
) -> dict:
    """Send scheduling emails to candidates."""
    # Get org for current user
    membership_query = (
        select(models.OrgMember)
        .where(models.OrgMember.supabase_user_id == current_session.user.id)
        .order_by(models.OrgMember.created_at)
    )
    membership_result = await session.execute(membership_query)
    membership = membership_result.scalar_one_or_none()
    
    if not membership:
        raise HTTPException(status_code=403, detail="No organization membership found")

    org_id = membership.org_id

    # Get invitations
    invitation_ids = [uuid.UUID(iid) for iid in payload.invitation_ids]
    invitations_result = await session.execute(
        select(models.Invitation)
        .where(models.Invitation.id.in_(invitation_ids))
        .options(selectinload(models.Invitation.assessment))
    )
    invitations = invitations_result.scalars().all()

    if len(invitations) != len(invitation_ids):
        raise HTTPException(status_code=404, detail="Some invitations not found")

    # Verify all invitations belong to user's org
    for invitation in invitations:
        if invitation.assessment.org_id != org_id:
            raise HTTPException(status_code=403, detail="Some invitations do not belong to your organization")

    # Send emails
    sent_count = 0
    failed_count = 0
    errors = []

    subject_template = payload.subject or "Meeting Invitation - {{assessment_title}}"
    body_template = payload.message or (
        "Hi {{candidate_name}},\n\n"
        "Thank you for completing the {{assessment_title}} assessment. "
        "We'd like to schedule a follow-up meeting to discuss your submission.\n\n"
        "Please book a time that works for you using the link below:\n\n"
        "{{booking_link}}\n\n"
        "We look forward to speaking with you!\n\n"
        "Best regards,\n"
        "The Team"
    )

    for invitation in invitations:
        try:
            # Build context
            context = {
                "candidate_name": invitation.candidate_name or invitation.candidate_email,
                "candidate_email": invitation.candidate_email,
                "assessment_title": invitation.assessment.title,
                "booking_link": payload.booking_url,
            }

            # Render template
            subject = subject_template
            body = body_template
            for key, value in context.items():
                subject = subject.replace(f"{{{{{key}}}}}", str(value))
                subject = subject.replace(f"{{{key}}}", str(value))
                body = body.replace(f"{{{{{key}}}}}", str(value))
                body = body.replace(f"{{{key}}}", str(value))

            # Send email
            html_body = "<br>".join(body.split("\n"))
            await email_service._send_email(
                to_email=invitation.candidate_email,
                subject=subject,
                text_body=body,
                html_body=html_body,
                context_label="scheduling",
            )

            # Record email event
            await email_service._record_email_event(
                session,
                invitation_id=invitation.id,
                event_type=models.EmailEventType.follow_up,
                provider_id=None,
                to_email=invitation.candidate_email,
                status="sent",
            )

            sent_count += 1
        except Exception as e:
            logger.error("Failed to send scheduling email to %s: %s", invitation.candidate_email, e)
            failed_count += 1
            errors.append(f"{invitation.candidate_email}: {str(e)}")

    await session.commit()

    return {
        "sent": sent_count,
        "failed": failed_count,
        "errors": errors,
    }


@router.post("/cal-com/webhook")
async def cal_com_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Receive webhook notifications from Cal.com about booking status changes.
    
    This endpoint should be configured in Cal.com webhook settings.
    Cal.com will POST to this endpoint when bookings are created, updated, or cancelled.
    """
    try:
        payload = await request.json()
        logger.info("Received Cal.com webhook: %s", payload)
        
        # Extract booking information from webhook payload
        # Cal.com webhook format varies, but typically includes:
        # - trigger: "BOOKING_CREATED", "BOOKING_CONFIRMED", "BOOKING_CANCELLED", etc.
        # - payload.data: booking data
        
        trigger = payload.get("trigger", "")
        booking_data = payload.get("data", {})
        
        # Extract Cal.com booking ID
        cal_booking_id = booking_data.get("id") or booking_data.get("bookingId") or booking_data.get("uid")
        
        # Extract attendee email to match with our invitations
        attendee_email = None
        if booking_data.get("attendees"):
            attendees = booking_data["attendees"]
            if isinstance(attendees, list) and len(attendees) > 0:
                attendee_email = attendees[0].get("email") if isinstance(attendees[0], dict) else None
        elif booking_data.get("responses"):
            attendee_email = booking_data["responses"].get("email") if isinstance(booking_data["responses"], dict) else None
        
        if not cal_booking_id and not attendee_email:
            logger.warning("Cal.com webhook missing booking ID and attendee email: %s", payload)
            return {"status": "ignored", "reason": "No booking ID or attendee email in webhook"}
        
        booking = None
        
        # Try to find booking by Cal.com booking ID first
        if cal_booking_id:
            booking_result = await session.execute(
                select(models.CalComBooking)
                .where(models.CalComBooking.booking_id == str(cal_booking_id))
            )
            booking = booking_result.scalar_one_or_none()
            
            # If not found, try to find by checking if booking_id contains the Cal.com booking ID
            if not booking:
                all_bookings_result = await session.execute(
                    select(models.CalComBooking)
                    .where(models.CalComBooking.booking_id.contains(str(cal_booking_id)))
                )
                booking = all_bookings_result.scalar_one_or_none()
        
        # If still not found and we have attendee email, try to match by invitation email
        if not booking and attendee_email:
            invitation_result = await session.execute(
                select(models.Invitation)
                .where(models.Invitation.candidate_email == attendee_email)
                .order_by(models.Invitation.created_at.desc())
            )
            invitation = invitation_result.scalar_one_or_none()
            
            if invitation:
                # Find the most recent booking link for this invitation
                booking_result = await session.execute(
                    select(models.CalComBooking)
                    .where(models.CalComBooking.invitation_id == invitation.id)
                    .order_by(models.CalComBooking.created_at.desc())
                )
                booking = booking_result.scalar_one_or_none()
        
        if booking:
            # Handle cancellation/rejection - delete the booking instead of marking as cancelled
            if trigger == "BOOKING_CANCELLED" or trigger == "BOOKING_REJECTED":
                await session.delete(booking)
                await session.commit()
                logger.info("Deleted booking %s from database (cancelled/rejected)", booking.id)
                return {"status": "deleted", "booking_id": str(booking.id)}
            
            # Update booking status based on trigger
            if trigger == "BOOKING_CREATED" or trigger == "BOOKING_CONFIRMED":
                booking.status = "confirmed"
            elif trigger == "BOOKING_RESCHEDULED":
                booking.status = "confirmed"
            
            # Update booking details if provided
            if booking_data.get("startTime") or booking_data.get("start"):
                start_time_str = booking_data.get("startTime") or booking_data.get("start")
                try:
                    booking.start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass
            
            if booking_data.get("endTime") or booking_data.get("end"):
                end_time_str = booking_data.get("endTime") or booking_data.get("end")
                try:
                    booking.end_time = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass
            
            if booking_data.get("title"):
                booking.title = booking_data.get("title")
            
            # Update the booking_id to the actual Cal.com booking ID if it's a confirmed booking
            if booking.status == "confirmed" and str(cal_booking_id) != booking.booking_id:
                booking.booking_id = str(cal_booking_id)
            
            await session.commit()
            logger.info("Updated booking %s status to %s", booking.id, booking.status)
            return {"status": "updated", "booking_id": str(booking.id)}
        else:
            logger.warning("Cal.com webhook for unknown booking ID: %s", cal_booking_id)
            return {"status": "ignored", "reason": "Booking not found"}
            
    except Exception as e:
        logger.error("Error processing Cal.com webhook: %s", e, exc_info=True)
        await session.rollback()
        # Return 200 to Cal.com so it doesn't retry
        return {"status": "error", "message": str(e)}


@router.post("/cal-com/sync-bookings")
async def sync_cal_com_bookings(
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "admin", "service_role")),
) -> dict:
    """Sync booking statuses from Cal.com API.
    
    This endpoint fetches the latest booking statuses from Cal.com
    and updates our database records. It:
    1. Syncs existing bookings by their Cal.com booking ID
    2. Finds new bookings created from our booking links by matching candidate emails
    """
    # Get org for current user
    membership_query = (
        select(models.OrgMember)
        .where(models.OrgMember.supabase_user_id == current_session.user.id)
        .order_by(models.OrgMember.created_at)
    )
    membership_result = await session.execute(membership_query)
    membership = membership_result.scalar_one_or_none()
    
    if not membership:
        raise HTTPException(status_code=403, detail="No organization membership found")

    org_id = membership.org_id

    try:
        cal_com_service = await _get_cal_com_service(session, org_id=org_id)
    except HTTPException:
        raise
    
    # Get all invitations for this org with their email addresses
    invitations_result = await session.execute(
        select(models.Invitation)
        .join(models.Assessment)
        .where(models.Assessment.org_id == org_id)
        .options(selectinload(models.Invitation.cal_com_bookings))
    )
    invitations = invitations_result.scalars().all()
    
    # Create a mapping of email to invitation
    email_to_invitation = {inv.candidate_email.lower(): inv for inv in invitations}
    
    # Get all our booking records for this org
    bookings_result = await session.execute(
        select(models.CalComBooking)
        .join(models.Invitation)
        .join(models.Assessment)
        .where(models.Assessment.org_id == org_id)
    )
    our_bookings = bookings_result.scalars().all()
    
    # Create mapping of booking_id to our booking record
    booking_id_map = {b.booking_id: b for b in our_bookings}
    
    # Create mapping of invitation_id to latest booking link
    invitation_booking_map = {}
    for booking in our_bookings:
        if booking.invitation_id:
            if booking.invitation_id not in invitation_booking_map:
                invitation_booking_map[booking.invitation_id] = booking
            elif booking.created_at > (invitation_booking_map[booking.invitation_id].created_at or datetime.min.replace(tzinfo=timezone.utc)):
                invitation_booking_map[booking.invitation_id] = booking
    
    updated_count = 0
    created_count = 0
    error_count = 0
    
    try:
        # Fetch all bookings from Cal.com
        logger.info("Fetching bookings from Cal.com...")
        cal_bookings_response = await cal_com_service.list_bookings(limit=100)
        cal_bookings = cal_bookings_response.get("bookings", [])
        if not cal_bookings and isinstance(cal_bookings_response, list):
            cal_bookings = cal_bookings_response
        
        logger.info("Found %d bookings in Cal.com", len(cal_bookings))
        
        # Process each Cal.com booking
        for cal_booking in cal_bookings:
            try:
                # Extract booking ID
                cal_booking_id = str(cal_booking.get("id") or cal_booking.get("bookingId") or cal_booking.get("uid") or "")
                
                if not cal_booking_id:
                    continue
                
                # Extract attendee email
                attendee_email = None
                if cal_booking.get("attendees"):
                    attendees = cal_booking["attendees"]
                    if isinstance(attendees, list) and len(attendees) > 0:
                        attendee_email = attendees[0].get("email") if isinstance(attendees[0], dict) else None
                elif cal_booking.get("responses"):
                    responses = cal_booking["responses"]
                    if isinstance(responses, dict):
                        attendee_email = responses.get("email")
                
                if not attendee_email:
                    continue
                
                attendee_email_lower = attendee_email.lower()
                
                # Find matching invitation
                invitation = email_to_invitation.get(attendee_email_lower)
                if not invitation:
                    continue
                
                # Check if we already have this booking
                existing_booking = booking_id_map.get(cal_booking_id)
                
                # Extract status - Cal.com uses different status formats
                status = cal_booking.get("status", "").lower()
                if status in ("accepted", "confirmed"):
                    status = "confirmed"
                elif status in ("pending", "awaiting"):
                    status = "pending"
                elif status in ("cancelled", "canceled", "rejected"):
                    # Delete cancelled bookings instead of keeping them
                    if existing_booking:
                        await session.delete(existing_booking)
                        logger.info("Deleted cancelled booking %s from database", existing_booking.id)
                        updated_count += 1
                    continue
                else:
                    # Default to confirmed if status is not clear but booking exists
                    status = "confirmed" if cal_booking_id else "pending"
                
                # Extract times
                start_time = None
                end_time = None
                
                if cal_booking.get("startTime") or cal_booking.get("start"):
                    start_time_str = cal_booking.get("startTime") or cal_booking.get("start")
                    try:
                        start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        pass
                
                if cal_booking.get("endTime") or cal_booking.get("end"):
                    end_time_str = cal_booking.get("endTime") or cal_booking.get("end")
                    try:
                        end_time = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        pass
                
                if existing_booking:
                    # Update existing booking
                    existing_booking.status = status
                    if start_time:
                        existing_booking.start_time = start_time
                    if end_time:
                        existing_booking.end_time = end_time
                    if cal_booking.get("title"):
                        existing_booking.title = cal_booking.get("title")
                    # Update booking_id if it was a link before
                    if existing_booking.booking_id.startswith("link-") and cal_booking_id:
                        existing_booking.booking_id = cal_booking_id
                    updated_count += 1
                else:
                    # Check if we have a pending booking link for this invitation
                    # If so, update it; otherwise create a new booking record
                    link_booking = invitation_booking_map.get(invitation.id)
                    if link_booking and link_booking.booking_id.startswith("link-"):
                        # Update the booking link to the actual booking
                        link_booking.booking_id = cal_booking_id
                        link_booking.status = status
                        link_booking.start_time = start_time
                        link_booking.end_time = end_time
                        if cal_booking.get("title"):
                            link_booking.title = cal_booking.get("title")
                        updated_count += 1
                    else:
                        # Create new booking record
                        new_booking = models.CalComBooking(
                            invitation_id=invitation.id,
                            booking_id=cal_booking_id,
                            event_type_id=str(cal_booking.get("eventTypeId", "")) if cal_booking.get("eventTypeId") else None,
                            booking_url=cal_booking.get("bookingUrl") or cal_booking.get("url"),
                            start_time=start_time,
                            end_time=end_time,
                            status=status,
                            title=cal_booking.get("title"),
                            description=cal_booking.get("description"),
                        )
                        session.add(new_booking)
                        booking_id_map[cal_booking_id] = new_booking
                        created_count += 1
                        
            except Exception as e:
                logger.warning("Error processing Cal.com booking: %s", e, exc_info=True)
                error_count += 1
                continue
        
        # Also sync existing bookings that have Cal.com booking IDs (not links)
        logger.info("Syncing existing bookings by ID...")
        for booking in our_bookings:
            # Skip if it's a booking link (we've already handled those above)
            if booking.booking_id.startswith("link-"):
                continue
            
            try:
                # Fetch latest status from Cal.com
                cal_booking = await cal_com_service.get_booking(booking.booking_id)
                
                # Update status
                status = cal_booking.get("status", "").lower()
                if status in ("accepted", "confirmed"):
                    booking.status = "confirmed"
                elif status in ("pending", "awaiting"):
                    booking.status = "pending"
                elif status in ("cancelled", "canceled", "rejected"):
                    # Delete cancelled bookings instead of keeping them
                    await session.delete(booking)
                    logger.info("Deleted cancelled booking %s from database", booking.id)
                    updated_count += 1
                    continue
                
                # Update times
                if cal_booking.get("startTime") or cal_booking.get("start"):
                    start_time_str = cal_booking.get("startTime") or cal_booking.get("start")
                    try:
                        booking.start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        pass
                
                if cal_booking.get("endTime") or cal_booking.get("end"):
                    end_time_str = cal_booking.get("endTime") or cal_booking.get("end")
                    try:
                        booking.end_time = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        pass
                
                if cal_booking.get("title"):
                    booking.title = cal_booking.get("title")
                
                updated_count += 1
                
            except CalComError as e:
                logger.warning("Failed to sync booking %s: %s", booking.booking_id, e)
                error_count += 1
                # If booking not found in Cal.com, delete it (was likely cancelled)
                if "404" in str(e) or "not found" in str(e).lower():
                    await session.delete(booking)
                    logger.info("Deleted booking %s (not found in Cal.com)", booking.id)
                    updated_count += 1
            except Exception as e:
                logger.warning("Unexpected error syncing booking %s: %s", booking.booking_id, e)
                error_count += 1
    
    except CalComError as e:
        logger.error("Failed to fetch bookings from Cal.com: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to sync bookings: {str(e)}")
    except Exception as e:
        logger.error("Unexpected error syncing bookings: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
    
    await session.commit()
    
    return {
        "updated": updated_count,
        "created": created_count,
        "errors": error_count,
        "total_processed": len(cal_bookings) if 'cal_bookings' in locals() else 0,
    }


@router.delete("/cal-com/bookings/{booking_id}")
async def delete_cal_com_booking(
    booking_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "admin", "service_role")),
) -> dict:
    """Delete a Cal.com booking.
    
    This will:
    1. Cancel the booking in Cal.com (if it's a confirmed booking with a Cal.com booking ID)
    2. Delete the booking record from our database
    """
    # Get org for current user
    membership_query = (
        select(models.OrgMember)
        .where(models.OrgMember.supabase_user_id == current_session.user.id)
        .order_by(models.OrgMember.created_at)
    )
    membership_result = await session.execute(membership_query)
    membership = membership_result.scalar_one_or_none()
    
    if not membership:
        raise HTTPException(status_code=403, detail="No organization membership found")

    org_id = membership.org_id

    # Find the booking record
    booking_result = await session.execute(
        select(models.CalComBooking)
        .join(models.Invitation)
        .join(models.Assessment)
        .where(models.Assessment.org_id == org_id)
        .where(models.CalComBooking.id == uuid.UUID(booking_id))
    )
    booking = booking_result.scalar_one_or_none()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # If this is a confirmed booking with a Cal.com booking ID (not a booking link),
    # cancel it in Cal.com first
    if booking.booking_id and not booking.booking_id.startswith("link-"):
        try:
            cal_com_service = await _get_cal_com_service(session, org_id=org_id)
            await cal_com_service.cancel_booking(booking.booking_id)
            logger.info("Cancelled booking %s in Cal.com", booking.booking_id)
        except CalComError as e:
            logger.warning("Failed to cancel booking in Cal.com: %s", e)
            # Continue with deletion from our database even if Cal.com cancellation fails
        except HTTPException:
            # If Cal.com service is not configured, just delete from our database
            pass

    # Delete the booking record from our database
    await session.delete(booking)
    await session.commit()

    logger.info("Deleted booking %s from database", booking_id)
    return {"success": True, "message": "Booking deleted successfully"}

