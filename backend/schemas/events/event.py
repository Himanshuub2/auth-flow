from datetime import datetime

from pydantic import BaseModel

from models.events.event import ApplicabilityType, EventStatus
from models.events.event_media_item import FileType


class FileMetadataIn(BaseModel):
    """Per-file metadata sent when saving an event. blob_path is the Azure path where FE uploaded the file."""
    original_filename: str
    blob_path: str
    file_type: FileType
    file_size_bytes: int
    caption: str | None = None
    description: str | None = None
    thumbnail_blob_path: str | None = None
    sort_order: int = 0


class EventSavePayload(BaseModel):
    event_name: str
    sub_event_name: str | None = None
    event_dates: list[str] | dict | None = None
    description: str | None = None
    tags: list[str] | None = None
    applicability_type: ApplicabilityType = ApplicabilityType.ALL
    applicability_refs: dict | list | None = None
    status: EventStatus = EventStatus.DRAFT
    file_metadata: list[FileMetadataIn] | None = None
    change_remarks: str | None = None


class UploadUrlRequest(BaseModel):
    """Optional existing event id; omit or null when creating a new event."""
    event_id: int | None = None


class UploadUrlResponse(BaseModel):
    """FE builds upload URL as: ``{base_url}{blob_path}?{sas_token}`` with ``blob_path`` like ``events/events-{slug}/file.jpg``."""
    slug: str
    base_path: str
    base_url: str
    sas_token: str


class MediaFileSummary(BaseModel):
    id: int
    original_filename: str
    file_type: FileType
    file_url: str
    blob_path: str
    thumbnail_url: str | None
    thumbnail_blob_path: str | None
    caption: str | None
    description: str | None
    media_versions: list[int]

    model_config = {"from_attributes": True}


class EventPreviewMediaItem(BaseModel):
    """Up to six thumbnails for the events list card."""

    id: int
    file_type: FileType
    thumbnail_url: str | None = None
    file_url: str


class EventListItemOut(BaseModel):
    """Paginated events feed: active events with preview media and likes."""

    id: int
    event_name: str
    sub_event_name: str | None
    event_dates: list | dict | None
    description: str | None
    tags: list | None
    like_count: int
    liked_by_me: bool
    preview_media: list[EventPreviewMediaItem]
    remaining_media_count: int


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
    applicability_refs: dict | list | None
    replaces_document_id: int | None = None
    created_by: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    change_remarks: str | None = None
    deactivate_remarks: str | None = None
    deactivated_at: datetime | None = None
    like_count: int = 0
    liked_by_me: bool = False
    files: list[MediaFileSummary]

    model_config = {"from_attributes": True}


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
    change_remarks: str | None = None
    deactivate_remarks: str | None = None
    status: str
    updated_at: datetime
    created_by: str
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
    change_remarks: str | None = None
    created_at: datetime
