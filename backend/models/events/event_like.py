from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import BaseEvents

SCHEMA = "events"
USERS_SCHEMA = "users"


class EventLike(BaseEvents):
    __tablename__ = "event_likes"
    __table_args__ = (
        UniqueConstraint("event_id", "staff_id", name="uq_event_likes_event_staff"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{SCHEMA}.events.id", ondelete="CASCADE"), nullable=False
    )
    staff_id: Mapped[str] = mapped_column(
        String(255), ForeignKey(f"{USERS_SCHEMA}.users.staff_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    event: Mapped["Event"] = relationship("Event", back_populates="likes", lazy="raise")
