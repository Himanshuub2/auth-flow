from datetime import date, datetime

from pydantic import BaseModel, field_validator

from models.documents.document import (
    ApplicabilityType,
    DocumentStatus,
    DocumentType,
    LABEL_TO_DOCUMENT_TYPE,
    document_type_to_label,
)
from models.documents.document_file import DocumentFileType


class DocumentSavePayload(BaseModel):
    name: str
    document_type: DocumentType
    tags: list[str]
    summary: str | None = None
    legislation_id: int | None = None
    sub_legislation_id: int | None = None
    version: int = 1
    next_review_date: date | None = None
    download_allowed: bool = True
    linked_document_ids: list[int] | None = None
    applicability_type: ApplicabilityType = ApplicabilityType.ALL
    applicability_refs: dict | list | None = None
    status: DocumentStatus = DocumentStatus.DRAFT
    selected_file_ids: list[int] | None = None
    change_remarks: str | None = None

    @field_validator("tags")
    @classmethod
    def tags_not_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one tag is required")
        return v

    @field_validator("linked_document_ids")
    @classmethod
    def max_linked(cls, v: list[int] | None) -> list[int] | None:
        if v is not None and len(v) > 6:
            raise ValueError("Maximum 6 linked items allowed")
        return v

    @field_validator("document_type", mode="before")
    @classmethod
    def document_type_to_enum(cls, v: str | DocumentType) -> DocumentType:
        if isinstance(v, DocumentType):
            return v
        s = (v or "").strip()
        try:
            return DocumentType(s)
        except ValueError:
            pass
        if s in LABEL_TO_DOCUMENT_TYPE:
            return LABEL_TO_DOCUMENT_TYPE[s]
        allowed = ", ".join(sorted(t.value for t in DocumentType))
        raise ValueError(f"Invalid document_type. Allowed constants: {allowed}")


class DeactivatePayload(BaseModel):
    deactivate_remarks: str

    @field_validator("deactivate_remarks")
    @classmethod
    def remarks_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Deactivate remarks cannot be empty")
        return v.strip()


class DocumentFileSummary(BaseModel):
    id: int
    original_filename: str
    file_type: DocumentFileType
    file_url: str
    media_versions: list[int]
    file_size_bytes: int

    model_config = {"from_attributes": True}


class LinkedDocumentDetail(BaseModel):
    id: int
    name: str
    document_type: str


class DocumentOut(BaseModel):
    id: int
    name: str
    document_type: str
    tags: list | None
    summary: str | None
    legislation_id: int | None
    sub_legislation_id: int | None
    next_review_date: date | None
    download_allowed: bool
    applicability_type: ApplicabilityType
    applicability_refs: dict | list | None
    status: DocumentStatus
    current_media_version: int
    current_revision_number: int
    change_remarks: str | None
    deactivate_remarks: str | None
    deactivated_by: str | None = None
    deactivated_at: datetime | None
    replaces_document_id: int | None = None
    created_by: str
    created_by_name: str
    updated_by: str | None = None
    created_at: datetime
    updated_at: datetime
    files: list[DocumentFileSummary]
    linked_document_details: list[LinkedDocumentDetail] | None = None

    model_config = {"from_attributes": True}


class DocumentRevisionOut(BaseModel):
    id: int
    document_id: int
    media_version: int
    revision_number: int
    version_display: str
    name: str
    document_type: str
    tags: list | None
    summary: str | None
    applicability_type: ApplicabilityType
    applicability_refs: dict | list | None
    change_remarks: str | None = None
    deactivate_remarks: str | None = None
    status: str
    updated_at: datetime
    created_by: str
    created_by_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RevisionListItemOut(BaseModel):
    id: int
    document_id: int
    media_version: int
    revision_number: int
    version_display: str
    created_at: datetime


class DocumentRevisionDetailOut(BaseModel):
    """Revision snapshot: revision metadata + files at that media version."""
    revision: DocumentRevisionOut
    files: list[DocumentFileSummary]


class DocumentHubItem(BaseModel):
    id: int
    name: str
    isNew: bool = False
    file_url: str | None = None

    model_config = {"from_attributes": True}


class DocumentHubCategory(BaseModel):
    document_type: str
    total: int
    new_count: int = 0
    items: list[DocumentHubItem]


class DocumentHubOut(BaseModel):
    categories: list[DocumentHubCategory]
