import enum
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import BaseDocuments

if TYPE_CHECKING:
    from models.documents.document_file import DocumentFile
    from models.events.user import User

SCHEMA = "documents"
USERS_SCHEMA = "users"

class DocumentType(str, enum.Enum):
    POLICY = "POLICY"
    GUIDANCE_NOTE = "GUIDANCE_NOTE"
    LAW_REGULATION = "LAW_REGULATION"
    TRAINING_MATERIAL = "TRAINING_MATERIAL"
    EWS = "EWS"
    FAQ = "FAQ"
    LATEST_NEWS_AND_ANNOUNCEMENTS = "LATEST_NEWS_AND_ANNOUNCEMENTS"
    FLYER = "FLYER"


DOCUMENT_TYPE_LABELS: dict[DocumentType, str] = {
    DocumentType.POLICY: "Policy",
    DocumentType.GUIDANCE_NOTE: "Guidance Note",
    DocumentType.LAW_REGULATION: "Law Regulation",
    DocumentType.TRAINING_MATERIAL: "Training Material",
    DocumentType.EWS: "EWS",
    DocumentType.FAQ: "FAQ",
    DocumentType.LATEST_NEWS_AND_ANNOUNCEMENTS: "Latest News and Announcements",
    DocumentType.FLYER: "Flyer",
}
LABEL_TO_DOCUMENT_TYPE: dict[str, DocumentType] = {v: k for k, v in DOCUMENT_TYPE_LABELS.items()}


def document_type_to_label(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return DOCUMENT_TYPE_LABELS[DocumentType(value)]
    except ValueError:
        return value


ROLE_DOCUMENT_TYPES: dict[str, list[DocumentType]] = {
    "policy_hub_admin": [
        DocumentType.POLICY,
        DocumentType.GUIDANCE_NOTE,
        DocumentType.LAW_REGULATION,
    ],
    "knowledge_hub_admin": [
        DocumentType.TRAINING_MATERIAL,
        DocumentType.EWS,
        DocumentType.FAQ,
        DocumentType.LATEST_NEWS_AND_ANNOUNCEMENTS,
        DocumentType.FLYER,
    ],
}


DOCUMENT_TYPE_ALLOWED_EXTENSIONS: dict[DocumentType, frozenset[str]] = {
    DocumentType.FAQ: frozenset({"xlsx"}),
    DocumentType.LATEST_NEWS_AND_ANNOUNCEMENTS: frozenset({
        "png", "jpg", "jpeg", "gif", "bmp", "tiff",
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    }),
    DocumentType.POLICY: frozenset({
        "png", "jpg", "jpeg", "gif", "bmp", "tiff",
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    }),
    DocumentType.GUIDANCE_NOTE: frozenset({
        "png", "jpg", "jpeg", "gif", "bmp", "tiff",
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    }),
    DocumentType.LAW_REGULATION: frozenset({
        "png", "jpg", "jpeg", "gif", "bmp", "tiff",
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    }),
    DocumentType.TRAINING_MATERIAL: frozenset({
        "png", "jpg", "jpeg", "gif", "bmp", "tiff",
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    }),
    DocumentType.EWS: frozenset({
        "png", "jpg", "jpeg", "gif", "bmp", "tiff",
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    }),
    DocumentType.FLYER: frozenset({
        "png", "jpg", "jpeg", "gif", "bmp", "tiff",
 
    }),
}


class DocumentStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class ApplicabilityType(str, enum.Enum):
    ALL = "ALL"
    DIVISION = "DIVISION"
    EMPLOYEE = "EMPLOYEE"


class Document(BaseDocuments):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type", schema=SCHEMA, create_constraint=True),
        nullable=False,
    )
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    legislation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(f"{SCHEMA}.legislation.id", ondelete="SET NULL"), nullable=True,
    )
    sub_legislation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(f"{SCHEMA}.sub_legislation.id", ondelete="SET NULL"), nullable=True,
    )

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    next_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    download_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    linked_document_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)

    applicability_type: Mapped[ApplicabilityType] = mapped_column(
        Enum(ApplicabilityType, name="doc_applicability_type", schema=SCHEMA, create_constraint=True),
        default=ApplicabilityType.ALL,
    )
    applicability_refs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", schema=SCHEMA, create_constraint=True),
        default=DocumentStatus.DRAFT,
    )

    current_media_version: Mapped[int] = mapped_column(Integer, default=0)
    current_revision_number: Mapped[int] = mapped_column(Integer, default=0)

    staging_file_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    change_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    deactivate_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_by: Mapped[str | None] = mapped_column(
        String(255), ForeignKey(f"{USERS_SCHEMA}.users.staff_id", ondelete="SET NULL"), nullable=True
    )

    replaces_document_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(f"{SCHEMA}.documents.id", ondelete="SET NULL"), nullable=True,
    )

    created_by: Mapped[str] = mapped_column(
        String(255), ForeignKey(f"{USERS_SCHEMA}.users.staff_id"), nullable=False,
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(255), ForeignKey(f"{USERS_SCHEMA}.users.staff_id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    revisions: Mapped[list["DocumentRevision"]] = relationship(
        back_populates="document", lazy="selectin",
        order_by="desc(DocumentRevision.media_version), desc(DocumentRevision.revision_number)",
    )
    files: Mapped[list["DocumentFile"]] = relationship(
        back_populates="document", lazy="selectin",
    )
    creator: Mapped["User"] = relationship(
        "User",
        foreign_keys=[created_by],
        primaryjoin="Document.created_by == User.staff_id",
        lazy="joined",
    )


class DocumentRevision(BaseDocuments):
    __tablename__ = "document_revisions"
    __table_args__ = (
        UniqueConstraint("document_id", "media_version", "revision_number", name="uq_doc_version_revision"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{SCHEMA}.documents.id", ondelete="CASCADE"), nullable=False,
    )
    media_version: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(
            Enum(DocumentType, name="document_type", schema=SCHEMA, create_constraint=True),
        nullable=False,
    )
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    applicability_type: Mapped[ApplicabilityType] = mapped_column(
        Enum(ApplicabilityType, name="doc_applicability_type", schema=SCHEMA, create_constraint=True),
        default=ApplicabilityType.ALL,
    )
    applicability_refs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    file_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    created_by: Mapped[str] = mapped_column(
        String(255), ForeignKey(f"{USERS_SCHEMA}.users.staff_id"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["Document"] = relationship(back_populates="revisions", lazy="raise")
    creator: Mapped["User"] = relationship(
        "User",
        foreign_keys=[created_by],
        primaryjoin="DocumentRevision.created_by == User.staff_id",
        lazy="joined",
    )
