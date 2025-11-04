"""SQLAlchemy ORM models for the coding interview platform backend."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Interval,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import BIGINT, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class InvitationStatus(enum.Enum):
    sent = "sent"
    accepted = "accepted"
    started = "started"
    submitted = "submitted"
    expired = "expired"
    revoked = "revoked"


class AccessScope(enum.Enum):
    clone = "clone"
    push = "push"
    clone_push = "clone+push"


class EmailEventType(enum.Enum):
    invite = "invite"
    reminder = "reminder"
    follow_up = "follow_up"
    assessment_started = "assessment_started"
    submission_received = "submission_received"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Org(Base, TimestampMixin):
    __tablename__ = "orgs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)

    members: Mapped[list["OrgMember"]] = relationship(back_populates="org")
    seeds: Mapped[list["Seed"]] = relationship(back_populates="org")
    email_templates: Mapped[list["EmailTemplate"]] = relationship(back_populates="org")
    github_installation: Mapped[Optional["GitHubInstallation"]] = relationship(
        back_populates="org", uselist=False
    )

class OrgMember(Base, TimestampMixin):
    __tablename__ = "org_members"
    __table_args__ = (
        UniqueConstraint("org_id", "supabase_user_id", name="uq_org_member"),
        CheckConstraint("role IN ('owner','admin','viewer')", name="ck_org_member_role"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True
    )
    supabase_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    org: Mapped[Org] = relationship(back_populates="members")


class GitHubInstallation(Base, TimestampMixin):
    __tablename__ = "github_installations"
    __table_args__ = (
        UniqueConstraint("installation_id", name="uq_github_installation_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    installation_id: Mapped[int] = mapped_column(BIGINT, nullable=False)
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    account_login: Mapped[str] = mapped_column(String, nullable=False)
    account_id: Mapped[int] = mapped_column(BIGINT, nullable=False)
    account_avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    account_html_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    installation_html_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    org: Mapped[Org] = relationship(back_populates="github_installation")


class GitHubInstallationState(Base, TimestampMixin):
    __tablename__ = "github_installation_states"
    __table_args__ = (Index("idx_github_installation_states_org_id", "org_id"),)
    __mapper_args__ = {"confirm_deleted_rows": False}

    token: Mapped[str] = mapped_column(String, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    return_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    org: Mapped[Org] = relationship()


class Seed(Base, TimestampMixin):
    __tablename__ = "seeds"
    __table_args__ = (Index("idx_seeds_org_id", "org_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    source_repo_url: Mapped[str] = mapped_column(Text, nullable=False)
    seed_repo_full_name: Mapped[str] = mapped_column(Text, nullable=False)
    default_branch: Mapped[str] = mapped_column(String, default="main", nullable=False)
    is_template: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    latest_main_sha: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    org: Mapped[Org] = relationship(back_populates="seeds")
    assessments: Mapped[list["Assessment"]] = relationship(back_populates="seed")


class Assessment(Base, TimestampMixin):
    __tablename__ = "assessments"
    __table_args__ = (Index("idx_assessments_org_id", "org_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    seed_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seeds.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    candidate_email_subject: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    candidate_email_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    time_to_start: Mapped[timedelta] = mapped_column(Interval, nullable=False)
    time_to_complete: Mapped[timedelta] = mapped_column(Interval, nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    rubric_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_mode: Mapped[Optional[str]] = mapped_column(
        String, default="auto", nullable=True
    )  # 'auto' or 'manual'

    org: Mapped[Org] = relationship()
    seed: Mapped[Seed] = relationship(back_populates="assessments")
    invitations: Mapped[list["Invitation"]] = relationship(back_populates="assessment")
    features: Mapped[list["AssessmentFeature"]] = relationship(back_populates="assessment")
    manual_rankings: Mapped[list["AssessmentManualRanking"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = (Index("idx_invitations_assessment_id", "assessment_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False
    )
    candidate_email: Mapped[str] = mapped_column(String, nullable=False)
    candidate_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(
            InvitationStatus,
            name="invitation_status",
            native_enum=False,
            validate_strings=True,
        ),
        default=InvitationStatus.sent,
        nullable=False,
    )
    start_deadline: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    complete_deadline: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    start_link_token_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    assessment: Mapped[Assessment] = relationship(back_populates="invitations")
    candidate_repo: Mapped[Optional["CandidateRepo"]] = relationship(
        back_populates="invitation", uselist=False
    )
    access_tokens: Mapped[list["AccessToken"]] = relationship(back_populates="invitation")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="invitation")
    review_comments: Mapped[list["ReviewComment"]] = relationship(back_populates="invitation")
    review_feedback: Mapped[list["ReviewFeedback"]] = relationship(back_populates="invitation")
    feature_scores: Mapped[list["ReviewFeatureScore"]] = relationship(back_populates="invitation")
    email_events: Mapped[list["EmailEvent"]] = relationship(back_populates="invitation")
    llm_analyses: Mapped[list["ReviewLLMAnalysis"]] = relationship(back_populates="invitation")
    llm_conversations: Mapped[list["ReviewLLMConversation"]] = relationship(back_populates="invitation")
    cal_com_bookings: Mapped[list["CalComBooking"]] = relationship(back_populates="invitation")


class CandidateRepo(Base, TimestampMixin):
    __tablename__ = "candidate_repos"
    __table_args__ = (
        Index("idx_candidate_repos_repo_full_name", "repo_full_name", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invitation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invitations.id", ondelete="CASCADE"), nullable=False
    )
    seed_sha_pinned: Mapped[str] = mapped_column(String, nullable=False)
    repo_full_name: Mapped[str] = mapped_column(String, nullable=False)
    repo_html_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    github_repo_id: Mapped[Optional[int]] = mapped_column(BIGINT, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    invitation: Mapped[Invitation] = relationship(back_populates="candidate_repo")


class AccessToken(Base, TimestampMixin):
    __tablename__ = "access_tokens"
    __table_args__ = (
        Index("idx_access_tokens_invitation_id", "invitation_id"),
        UniqueConstraint("opaque_token_hash", name="uq_access_token_hash"),
        CheckConstraint(
            "scope IN ('clone','push','clone+push')",
            name="ck_access_token_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invitation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invitations.id", ondelete="CASCADE"), nullable=False
    )
    repo_full_name: Mapped[str] = mapped_column(String, nullable=False)
    opaque_token_hash: Mapped[str] = mapped_column(String, nullable=False)
    scope: Mapped[AccessScope] = mapped_column(
        Enum(
            AccessScope,
            name="access_scope",
            native_enum=False,
            validate_strings=True,
            create_constraint=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=AccessScope.clone_push,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    invitation: Mapped[Invitation] = relationship(back_populates="access_tokens")


class Submission(Base, TimestampMixin):
    __tablename__ = "submissions"
    __table_args__ = (Index("idx_submissions_invitation_id", "invitation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invitation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invitations.id", ondelete="CASCADE"), nullable=False
    )
    final_sha: Mapped[str] = mapped_column(String, nullable=False)
    repo_html_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    video_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    invitation: Mapped[Invitation] = relationship(back_populates="submissions")


class ReviewComment(Base, TimestampMixin):
    __tablename__ = "review_comments"
    __table_args__ = (Index("idx_review_comments_invitation_id", "invitation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invitation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invitations.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    line: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    invitation: Mapped[Invitation] = relationship(back_populates="review_comments")


class ReviewFeedback(Base, TimestampMixin):
    __tablename__ = "review_feedback"
    __table_args__ = (Index("idx_review_feedback_invitation_id", "invitation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invitation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invitations.id", ondelete="CASCADE"), nullable=False
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    calculated_score: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    max_score: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    invitation: Mapped[Invitation] = relationship(back_populates="review_feedback")


class AssessmentFeature(Base, TimestampMixin):
    __tablename__ = "assessment_features"
    __table_args__ = (
        UniqueConstraint("assessment_id", "name", name="uq_assessment_feature_name"),
        Index("idx_assessment_features_assessment_id", "assessment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    weight: Mapped[float] = mapped_column(Numeric(10, 2), default=1.0, nullable=False)

    assessment: Mapped["Assessment"] = relationship(back_populates="features")
    scores: Mapped[list["ReviewFeatureScore"]] = relationship(back_populates="feature")


class ReviewFeatureScore(Base, TimestampMixin):
    __tablename__ = "review_feature_scores"
    __table_args__ = (
        UniqueConstraint("invitation_id", "feature_id", name="uq_review_feature_score"),
        Index("idx_review_feature_scores_invitation_id", "invitation_id"),
        Index("idx_review_feature_scores_feature_id", "feature_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invitation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invitations.id", ondelete="CASCADE"), nullable=False
    )
    feature_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_features.id", ondelete="CASCADE"), nullable=False
    )
    checked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    invitation: Mapped["Invitation"] = relationship(back_populates="feature_scores")
    feature: Mapped["AssessmentFeature"] = relationship(back_populates="scores")


class AssessmentManualRanking(Base, TimestampMixin):
    __tablename__ = "assessment_manual_rankings"
    __table_args__ = (
        UniqueConstraint("assessment_id", "invitation_id", name="uq_assessment_manual_ranking"),
        Index("idx_assessment_manual_rankings_assessment_id", "assessment_id"),
        Index("idx_assessment_manual_rankings_display_order", "assessment_id", "display_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False
    )
    invitation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invitations.id", ondelete="CASCADE"), nullable=False
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    assessment: Mapped["Assessment"] = relationship(back_populates="manual_rankings")
    invitation: Mapped["Invitation"] = relationship()


class EmailTemplate(Base, TimestampMixin):
    __tablename__ = "email_templates"
    __table_args__ = (UniqueConstraint("org_id", "key", name="uq_email_template_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    org: Mapped[Org] = relationship(back_populates="email_templates")


class EmailEvent(Base, TimestampMixin):
    __tablename__ = "email_events"
    __table_args__ = (Index("idx_email_events_invitation_id", "invitation_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invitation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invitations.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[Optional[EmailEventType]] = mapped_column(
        Enum(
            EmailEventType,
            name="email_event_type",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=True,
    )
    provider_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    to_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    invitation: Mapped[Invitation] = relationship(back_populates="email_events")


class ReviewLLMAnalysis(Base, TimestampMixin):
    __tablename__ = "review_llm_analyses"
    __table_args__ = (
        Index("idx_review_llm_analyses_invitation_id", "invitation_id"),
        Index("idx_review_llm_analyses_created_at", "created_at"),
        UniqueConstraint("invitation_id", name="uq_review_llm_analysis_invitation"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invitation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invitations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    analysis_text: Mapped[str] = mapped_column(Text, nullable=False)
    raw_response: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    invitation: Mapped[Invitation] = relationship(back_populates="llm_analyses")


class ReviewLLMConversation(Base):
    __tablename__ = "review_llm_conversations"
    __table_args__ = (
        Index("idx_review_llm_conversations_invitation_id", "invitation_id", "created_at"),
        CheckConstraint("message_type IN ('user', 'assistant')", name="ck_conversation_message_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invitation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invitations.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_type: Mapped[str] = mapped_column(String, nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    context_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    invitation: Mapped[Invitation] = relationship(back_populates="llm_conversations")


class CalComConfig(Base, TimestampMixin):
    __tablename__ = "cal_com_configs"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True
    )
    api_key: Mapped[str] = mapped_column(Text, nullable=False)
    api_url: Mapped[str] = mapped_column(
        Text, default="https://api.cal.com/v1", nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    org: Mapped[Org] = relationship()


class CalComBooking(Base, TimestampMixin):
    __tablename__ = "cal_com_bookings"
    __table_args__ = (
        Index("idx_cal_com_bookings_invitation_id", "invitation_id"),
        Index("idx_cal_com_bookings_booking_id", "booking_id"),
        Index("idx_cal_com_bookings_start_time", "start_time"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invitation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invitations.id", ondelete="CASCADE"), nullable=True
    )
    booking_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    event_type_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    booking_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    invitation: Mapped[Optional["Invitation"]] = relationship(back_populates="cal_com_bookings")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("idx_audit_events_kind", "kind"),
        Index("idx_audit_events_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    kind: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    actor: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

