from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import BaseEvents

if TYPE_CHECKING:
    from models.events.event import Event

SCHEMA = "events"


class FileType(str, enum.Enum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"


class EventMediaItem(BaseEvents):
    __tablename__ = "files"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{SCHEMA}.events.id", ondelete="CASCADE"), nullable=False
    )

    file_type: Mapped[FileType] = mapped_column(
        Enum(FileType, name="file_type", schema=SCHEMA, create_constraint=True), nullable=False
    )
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    caption: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    event: Mapped["Event"] = relationship(back_populates="media_items", lazy="raise")
