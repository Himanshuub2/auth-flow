
from app.models.event import Event
from app.schemas.event import EventOut, MediaFileSummary


def _to_out(event: Event) -> EventOut:
    ver = event.current_media_version
    target_ver = ver if ver > 0 else 0
    files = [
        MediaFileSummary.model_validate(m)
        for m in event.media_items
        if target_ver in m.media_versions
    ]
    return EventOut(
        id=event.id,
        event_name=event.event_name,
        sub_event_name=event.sub_event_name,
        event_dates=event.event_dates,
        description=event.description,
        tags=event.tags,
        current_media_version=ver,
        current_revision_number=event.current_revision_number,
        version_display=f"{ver}.{event.current_revision_number}",
        status=event.status,
        applicability_type=event.applicability_type,
        applicability_refs=event.applicability_refs,
        draft_parent_id=event.draft_parent_id,
        created_by=event.created_by,
        created_by_name=event.creator.full_name,
        created_at=event.created_at,
        updated_at=event.updated_at,
        files=files,
    )


def _to_list_out(event: Event) -> EventOut:
    """Build EventOut for list endpoint without loading media_items (only basic fields + creator via join)."""
    ver = event.current_media_version
    return EventOut(
        id=event.id,
        event_name=event.event_name,
        sub_event_name=event.sub_event_name,
        event_dates=event.event_dates,
        description=event.description,
        tags=event.tags,
        current_media_version=ver,
        current_revision_number=event.current_revision_number,
        version_display=f"{ver}.{event.current_revision_number}",
        status=event.status,
        applicability_type=event.applicability_type,
        applicability_refs=event.applicability_refs,
        draft_parent_id=event.draft_parent_id,
        created_by=event.created_by,
        created_by_name=event.creator.full_name,
        created_at=event.created_at,
        updated_at=event.updated_at,
        files=[],
    )