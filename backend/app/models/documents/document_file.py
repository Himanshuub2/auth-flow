import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import BaseDocuments

SCHEMA = "documents"


class DocumentFileType(str, enum.Enum):
    IMAGE = "IMAGE"
    DOCUMENT = "DOCUMENT"


class DocumentFile(BaseDocuments):
    __tablename__ = "files"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{SCHEMA}.documents.id", ondelete="CASCADE"), nullable=False,
    )

    media_versions: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False, default=list)

    file_type: Mapped[DocumentFileType] = mapped_column(
        Enum(DocumentFileType, name="doc_file_type", schema=SCHEMA, create_constraint=True),
        nullable=False,
    )
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["Document"] = relationship(back_populates="files", lazy="raise")
