import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FileType(str, enum.Enum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"


class EventMediaItem(Base):
    __tablename__ = "files"
    __table_args__ = (
        Index("ix_event_media_version", "event_id", "media_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    media_version: Mapped[int] = mapped_column(Integer, nullable=False)

    file_type: Mapped[FileType] = mapped_column(
        Enum(FileType, name="file_type", create_constraint=True), nullable=False
    )
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    caption: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # raise: prevents accidental lazy load — load explicitly when needed
    event: Mapped["Event"] = relationship(back_populates="media_items", lazy="raise")
