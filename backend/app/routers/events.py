from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.event import Event, EventStatus
from app.models.user import User
from app.schemas.event import EventListOut, EventOut, EventSavePayload, MediaFileSummary
from app.services import event_service
from app.utils.security import get_current_user

router = APIRouter()


def _to_out(event: Event) -> EventOut:
    ver = event.current_media_version
    # For drafts (ver==0) show staging files; otherwise show current version
    target_ver = ver if ver > 0 else 0
    files = [
        MediaFileSummary.model_validate(m)
        for m in event.media_items
        if m.media_version == target_ver
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


@router.post("/", response_model=EventOut, status_code=201)
async def create_event(
    data: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload = EventSavePayload.model_validate_json(data)
    event = await event_service.save_event(db, user.id, payload, files=files or None)
    return _to_out(event)


@router.put("/{event_id}", response_model=EventOut)
async def update_event(
    event_id: int,
    data: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload = EventSavePayload.model_validate_json(data)
    event = await event_service.save_event(db, user.id, payload, event_id=event_id, files=files or None)
    return _to_out(event)


@router.get("/", response_model=EventListOut)
async def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: EventStatus | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    events, total = await event_service.list_events(db, page, page_size, status)
    return EventListOut(
        items=[_to_out(e) for e in events],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{event_id}", response_model=EventOut)
async def get_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = await event_service.get_event(db, event_id)
    return _to_out(event)


@router.post("/{event_id}/draft", response_model=EventOut, status_code=201)
async def create_draft_from_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    draft = await event_service.create_draft_from_event(db, event_id, user.id)
    return _to_out(draft)


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await event_service.delete_event(db, event_id)
