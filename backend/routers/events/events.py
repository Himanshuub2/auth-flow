import asyncio

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from cache import cache_delete, cache_delete_prefix
from database import get_db
from models.events.event import Event, EventStatus
from schemas.events.comman import APIResponse, APIResponsePaginated
from schemas.events.event import EventSavePayload, UploadUrlRequest, UploadUrlResponse
from services.events import event_like_service
from services.events import event_service
from services.events.upload_url_service import generate_upload_urls
from utils import cache_keys
from utils.security import CurrentUser, get_current_user
from pydantic import BaseModel


class ToggleEventPayload(BaseModel):
    """Required when deactivating (ACTIVE -> INACTIVE). Optional when reactivating."""

    deactivate_remarks: str | None = None


router = APIRouter()


def _minimal_event_data(event: Event) -> dict[str, int | str]:
    return {"id": event.id, "name": event.event_name}


@router.post("/upload-url", response_model=APIResponse)
async def get_upload_urls(
    body: UploadUrlRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    result = await generate_upload_urls(db, body)
    return APIResponse(
        message="Upload URLs generated",
        status_code=200,
        status="success",
        data=result.model_dump(),
    )


@router.post("/", response_model=APIResponse, status_code=201)
async def create_event(
    payload: EventSavePayload,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    event = await event_service.save_event(db, user.id, payload)
    await cache_delete(cache_keys.event_item(event.id))
    await cache_delete_prefix("events:list:")
    await cache_delete_prefix("items:list:")
    await cache_delete("items:kpi")
    return APIResponse(message="Event created", status_code=201, status="success", data=_minimal_event_data(event))


@router.put("/{event_id}", response_model=APIResponse)
async def update_event(
    event_id: int,
    payload: EventSavePayload,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    event = await event_service.save_event(db, user.id, payload, event_id=event_id)
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
    status: EventStatus | None = Query(
        None,
        description="Omit for ACTIVE-only (default). Pass DRAFT/INACTIVE to filter admin views.",
    ),
    search: str | None = Query(
        None,
        max_length=500,
        description="Case-insensitive match on event name, description, or tags.",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    events, total = await event_service.list_events(db, page, page_size, status, search)
    event_ids = [e.id for e in events]
    liked_ids = await event_like_service.event_ids_liked_by_user(db, user.id, event_ids)
    file_ids_list = await asyncio.gather(
        *[event_service.get_file_ids_for_event_list_card(db, e) for e in events]
    )
    data = [
        event_service.build_event_list_card(e, ids, liked_by_me=(e.id in liked_ids))
        for e, ids in zip(events, file_ids_list)
    ]
    return APIResponsePaginated(
        message="Events fetched",
        status_code=200,
        status="success",
        data=data,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{event_id}/like", response_model=APIResponse)
async def like_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    count, _ = await event_like_service.like_event(db, event_id, user.id)
    await cache_delete_prefix("events:list:")
    await cache_delete(cache_keys.event_item(event_id))
    await cache_delete_prefix("items:list:")
    await cache_delete("items:kpi")
    return APIResponse(
        message="Liked",
        status_code=200,
        status="success",
        data={"like_count": count, "liked_by_me": True},
    )


@router.delete("/{event_id}/like", response_model=APIResponse)
async def unlike_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    count, _ = await event_like_service.unlike_event(db, event_id, user.id)
    await cache_delete_prefix("events:list:")
    await cache_delete(cache_keys.event_item(event_id))
    await cache_delete_prefix("items:list:")
    await cache_delete("items:kpi")
    return APIResponse(
        message="Unliked",
        status_code=200,
        status="success",
        data={"like_count": count, "liked_by_me": False},
    )


@router.get("/{event_id}", response_model=APIResponse)
async def get_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    event = await event_service.get_event_with_relations(db, event_id)
    liked = await event_like_service.is_liked(db, user.id, event_id)
    out = event_service.build_event_out(event, liked_by_me=liked)
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
