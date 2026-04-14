from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import BaseEvents

SCHEMA = "events"
USERS_SCHEMA = "users"


class EventStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class ApplicabilityType(str, enum.Enum):
    ALL = "ALL"
    DIVISION = "DIVISION"
    EMPLOYEE = "EMPLOYEE"


class Event(BaseEvents):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    event_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    sub_event_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_dates: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    current_media_version: Mapped[int] = mapped_column(Integer, default=0)
    current_revision_number: Mapped[int] = mapped_column(Integer, default=0)

    staging_file_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, name="event_status", schema=SCHEMA, create_constraint=True),
        default=EventStatus.DRAFT,
    )

    applicability_type: Mapped[ApplicabilityType] = mapped_column(
        Enum(ApplicabilityType, name="applicability_type", schema=SCHEMA, create_constraint=True),
        default=ApplicabilityType.ALL,
    )
    applicability_refs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    replaces_document_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(f"{SCHEMA}.events.id", ondelete="SET NULL"), nullable=True
    )

    created_by: Mapped[str] = mapped_column(String(255), ForeignKey(f"{USERS_SCHEMA}.users.staff_id"), nullable=False)
    updated_by: Mapped[str | None] = mapped_column(
        String(255), ForeignKey(f"{USERS_SCHEMA}.users.staff_id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    change_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    deactivate_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_by: Mapped[str | None] = mapped_column(
        String(255), ForeignKey(f"{USERS_SCHEMA}.users.staff_id", ondelete="SET NULL"), nullable=True
    )

    revisions: Mapped[list["EventRevision"]] = relationship(
        back_populates="event", lazy="selectin",
        order_by="desc(EventRevision.media_version), desc(EventRevision.revision_number)",
    )
    media_items: Mapped[list["EventMediaItem"]] = relationship(
        back_populates="event", lazy="selectin",
    )
    creator: Mapped["User"] = relationship(lazy="joined", foreign_keys=[created_by])

    like_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    likes: Mapped[list["EventLike"]] = relationship(
        "EventLike",
        back_populates="event",
        lazy="select",
        cascade="all, delete-orphan",
    )


class EventRevision(BaseEvents):
    """Immutable snapshot created only when an event is published."""
    __tablename__ = "event_revisions"
    __table_args__ = (
        UniqueConstraint("event_id", "media_version", "revision_number", name="uq_event_version_revision"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{SCHEMA}.events.id", ondelete="CASCADE"), nullable=False
    )
    media_version: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)

    event_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sub_event_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_dates: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    file_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    created_by: Mapped[str] = mapped_column(String(255), ForeignKey(f"{USERS_SCHEMA}.users.staff_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    change_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    event: Mapped["Event"] = relationship(back_populates="revisions", lazy="raise")
    creator: Mapped["User"] = relationship(lazy="joined", foreign_keys=[created_by])
