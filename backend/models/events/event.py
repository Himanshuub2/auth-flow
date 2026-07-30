from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from utils.dates import ist_now
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import BaseEvents
from utils.dates import format_event_date_range, parse_event_date_range

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
    event_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    event_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    version: Mapped[float] = mapped_column(Numeric(10, 2), default=1.0, nullable=False, server_default="1.0")
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False, server_default="1")

    staging_file_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, name="event_status", schema=SCHEMA, create_constraint=True),
        default=EventStatus.DRAFT,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    applicability_type: Mapped[ApplicabilityType] = mapped_column(
        Enum(ApplicabilityType, name="applicability_type", schema=SCHEMA, create_constraint=True),
        default=ApplicabilityType.ALL,
    )
    applicability_refs: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    replaces_document_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(f"{SCHEMA}.events.id", ondelete="SET NULL"), nullable=True
    )

    created_by: Mapped[str] = mapped_column(String(255), ForeignKey(f"{USERS_SCHEMA}.users.staff_id"), nullable=False)
    updated_by: Mapped[str | None] = mapped_column(
        String(255), ForeignKey(f"{USERS_SCHEMA}.users.staff_id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ist_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ist_now, onupdate=ist_now
    )
    change_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    deactivate_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_by: Mapped[str | None] = mapped_column(
        String(255), ForeignKey(f"{USERS_SCHEMA}.users.staff_id", ondelete="SET NULL"), nullable=True
    )

    revisions: Mapped[list["EventRevision"]] = relationship(
        back_populates="event", lazy="selectin",
        order_by="desc(EventRevision.revision_number), desc(EventRevision.media_version)",
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

    @property
    def event_dates(self) -> list[str] | None:
        return format_event_date_range(self.event_start, self.event_end)

    @event_dates.setter
    def event_dates(self, value: list[str] | None) -> None:
        self.event_start, self.event_end = parse_event_date_range(value)


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
    media_version: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)

    event_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sub_event_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    event_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    applicability_type: Mapped[ApplicabilityType] = mapped_column(
        Enum(ApplicabilityType, name="applicability_type", schema=SCHEMA, create_constraint=True),
        nullable=False,
        default=ApplicabilityType.ALL,
    )
    applicability_refs: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    file_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    created_by: Mapped[str] = mapped_column(String(255), ForeignKey(f"{USERS_SCHEMA}.users.staff_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ist_now
    )
    change_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    event: Mapped["Event"] = relationship(back_populates="revisions", lazy="raise")
    creator: Mapped["User"] = relationship(lazy="joined", foreign_keys=[created_by])

    @property
    def event_dates(self) -> list[str] | None:
        return format_event_date_range(self.event_start, self.event_end)

    @event_dates.setter
    def event_dates(self, value: list[str] | None) -> None:
        self.event_start, self.event_end = parse_event_date_range(value)
