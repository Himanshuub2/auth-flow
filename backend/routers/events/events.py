from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from cache import cache_delete, cache_delete_prefix, cache_get, cache_set
from config import settings
from database import get_db
from models.events.event import Event, EventStatus
from schemas.events.comman import APIResponse, APIResponsePaginated
from schemas.events.event import EventOut, EventSavePayload
from services.events import event_service
from utils import cache_keys
from utils.dates import format_date_dmy_month_abbr
from utils.security import CurrentUser, get_current_user
from pydantic import BaseModel


class ToggleEventPayload(BaseModel):
    """Required when deactivating (ACTIVE -> INACTIVE). Optional when reactivating."""

    deactivate_remarks: str | None = None


router = APIRouter()
EVENT_LIST_CACHE_TTL = getattr(settings, "ITEM_DETAIL_CACHE_TTL_SECONDS", 300)


def _minimal_event_data(event: Event) -> dict[str, int | str]:
    return {"id": event.id, "name": event.event_name}


def _to_out(event: Event) -> EventOut:
    from services.events.event_service import build_event_out
    return build_event_out(event)


def _to_list_out(event: Event) -> EventOut:
    """Event for list endpoint: same as _to_out but files=[] (media not loaded)."""
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
        replaces_document_id=event.replaces_document_id,
        created_by=event.created_by,
        created_by_name=event.creator.username,
        created_at=event.created_at,
        updated_at=event.updated_at,
        change_remarks=event.change_remarks,
        deactivate_remarks=event.deactivate_remarks,
        deactivated_at=format_date_dmy_month_abbr(event.deactivated_at) if event.deactivated_at else None,
        files=[],
    )


@router.post("/", response_model=APIResponse, status_code=201)
async def create_event(
    data: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    payload = EventSavePayload.model_validate_json(data)
    event = await event_service.save_event(db, user.id, payload, files=files or None)
    await cache_delete(cache_keys.event_item(event.id))
    await cache_delete_prefix("events:list:")
    await cache_delete_prefix("items:list:")
    await cache_delete("items:kpi")
    return APIResponse(message="Event created", status_code=201, status="success", data=_minimal_event_data(event))


@router.put("/{event_id}", response_model=APIResponse)
async def update_event(
    event_id: int,
    data: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    payload = EventSavePayload.model_validate_json(data)
    event = await event_service.save_event(db, user.id, payload, event_id=event_id, files=files or None)
    await cache_delete(cache_keys.event_item(event_id))
    if event.id != event_id:
        await cache_delete(cache_keys.event_item(event.id))
    await cache_delete_prefix("events:list:")
    await cache_delete_prefix("items:list:")
    await cache_delete("items:kpi")
    return APIResponse(message="Event updated", status_code=200, status="success", data=_minimal_event_data(event))


@router.get("/", response_model=APIResponsePaginated)
async def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: EventStatus | None = None,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    cache_key = cache_keys.event_list(page, page_size, status.value if status else None)
    cached = await cache_get(cache_key)
    if cached is not None:
        return APIResponsePaginated(**cached)

    events, total = await event_service.list_events(db, page, page_size, status)
    response = APIResponsePaginated(
        message="Events fetched",
        status_code=200,
        status="success",
        data=[_to_list_out(e) for e in events],
        total=total,
        page=page,
        page_size=page_size,
    )
    await cache_set(cache_key, response.model_dump(mode="json"), ttl=EVENT_LIST_CACHE_TTL)
    return response


@router.get("/{event_id}", response_model=APIResponse)
async def get_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    cache_key = cache_keys.event_item(event_id)
    cached = await cache_get(cache_key)
    if cached is not None:
        return APIResponse(message="Event fetched", status_code=200, status="success", data=cached)

    event = await event_service.get_event_with_relations(db, event_id)
    out = _to_out(event)
    await cache_set(cache_key, out.model_dump(mode="json"), ttl=EVENT_LIST_CACHE_TTL)
    return APIResponse(message="Event fetched", status_code=200, status="success", data=out)


@router.patch("/{event_id}/toggle-status", response_model=APIResponse)
async def toggle_event_status(
    event_id: int,
    payload: ToggleEventPayload | None = Body(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    remarks = payload.deactivate_remarks if payload else None
    event = await event_service.toggle_event_status(db, event_id, user.id, deactivate_remarks=remarks)
    await cache_delete(cache_keys.event_item(event_id))
    await cache_delete_prefix("events:list:")
    await cache_delete_prefix("items:list:")
    await cache_delete("items:kpi")
    return APIResponse(message="Status updated", status_code=200, status="success", data=_minimal_event_data(event))
