"""Schemas for items KPI and filter APIs."""

from datetime import date

from pydantic import BaseModel, Field


class ItemsListBody(BaseModel):
    """Payload for POST /api/items/ (list with filters and pagination). All fields optional."""

    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(20, ge=1, le=100, description="Items per page")
    item_type: str | None = Field(None, description="Filter by 'event' or 'document'")
    document_types: list[str] | None = Field(None, description="Filter by type: Policy, Guidance Note, EWS, event, etc.")
    document_names: list[str] | None = Field(None, description="Filter by exact name(s)")
    statuses: list[str] | None = Field(None, description="Filter by status: DRAFT, ACTIVE, INACTIVE")
    last_updated_start: date | None = Field(None, description="Last updated from date")
    last_updated_end: date | None = Field(None, description="Last updated to date")
    next_review_start: date | None = Field(None, description="Next review from date")
    next_review_end: date | None = Field(None, description="Next review to date")
    search: str | None = Field(None, description="Search in document/event name (ILIKE)")


class ItemsKpiOut(BaseModel):
    """KPI counts: active, draft, by_type; overdue/due_for_review based on next_review_date."""

    active_doc: int = Field(description="Count of active documents + events")
    due_for_review: int = Field(description="Documents with next_review_date >= today")
    overdue: int = Field(description="Documents with next_review_date < today")
    draft: int = Field(description="Count of draft documents + events")

    by_type: dict[str, int] = Field(
        default_factory=dict,
        description="Count per type: Policy, Guidance Note, etc., plus Event",
    )
