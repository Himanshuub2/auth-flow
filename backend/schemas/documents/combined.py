from datetime import date, datetime

from pydantic import BaseModel


class CombinedItemOut(BaseModel):
    """Unified row for the combined events + documents table. document_type is the doc type (Policy, EWS, etc.) or 'event' for events."""
    id: int
    name: str
    document_type: str  # document type label for docs; "event" for events
    version_display: str
    status: str
    created_by: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    deactivated_by: str | None = None
    deactivated_by_name: str | None = None
    deactivated_at: datetime | None = None
    next_review_date: date | None = None
    revision: int
    version: int


class ItemRevisionListItemOut(BaseModel):
    """Unified revision list row for events and documents."""
    id: int
    media_version: int
    revision_number: int
    version_display: str
    created_at: datetime
    change_remarks: str | None = None
    event_id: int | None = None
    document_id: int | None = None
