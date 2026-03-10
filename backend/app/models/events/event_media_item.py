import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import BaseEvents
from app.db_utils import (
    events_table,
    fk_events,
    schema_events,
)


class FileType(str, enum.Enum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"


class EventMediaItem(BaseEvents):
    __tablename__ = events_table("files")
    __table_args__ = ({"schema": schema_events()},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(fk_events("events"), ondelete="CASCADE"), nullable=False
    )

    file_type: Mapped[FileType] = mapped_column(
        Enum(FileType, name="file_type", schema=schema_events(), create_constraint=True), nullable=False
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
