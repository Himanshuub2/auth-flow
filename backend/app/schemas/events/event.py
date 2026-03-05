from datetime import datetime

from pydantic import BaseModel

from app.models.events.event import ApplicabilityType, EventStatus
from app.models.events.event_media_item import FileType


class FileMetadataIn(BaseModel):
    """Per-file caption, description, and optional thumbnail (for video)."""
    original_filename: str
    caption: str | None = None
    description: str | None = None
    thumbnail_original_filename: str | None = None


class EventSavePayload(BaseModel):
    event_name: str
    sub_event_name: str | None = None
    event_dates: list[str] | dict | None = None
    description: str | None = None
    tags: list[str] | None = None
    applicability_type: ApplicabilityType = ApplicabilityType.ALL
    applicability_refs: dict | None = None
    status: EventStatus = EventStatus.DRAFT
    selected_filenames: list[str] | None = None
    file_metadata: list[FileMetadataIn] | None = None


class MediaFileSummary(BaseModel):
    id: int
    original_filename: str
    file_type: FileType
    file_url: str
    thumbnail_url: str | None
    caption: str | None
    description: str | None
    media_versions: list[int]

    model_config = {"from_attributes": True}


class EventOut(BaseModel):
    id: int
    event_name: str
    sub_event_name: str | None
    event_dates: list | dict | None
    description: str | None
    tags: list | None
    current_media_version: int
    current_revision_number: int
    version_display: str
    status: EventStatus
    applicability_type: ApplicabilityType
    applicability_refs: dict | None
    draft_parent_id: int | None
    created_by: int
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    files: list[MediaFileSummary]

    model_config = {"from_attributes": True}


class EventListOut(BaseModel):
    items: list[EventOut]
    total: int
    page: int
    page_size: int


class RevisionOut(BaseModel):
    id: int
    event_id: int
    media_version: int
    revision_number: int
    version_display: str
    event_name: str
    sub_event_name: str | None
    event_dates: list | dict | None
    description: str | None
    tags: list | None
    created_by: int
    created_by_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RevisionListItemOut(BaseModel):
    """Slim version used for list_revisions."""

    id: int
    event_id: int
    media_version: int
    revision_number: int
    version_display: str
    created_at: datetime
