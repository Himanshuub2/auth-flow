from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cache import cache_delete, cache_delete_prefix
from database import get_db
from models.events.event import ApplicabilityType, Event, EventStatus
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
    search: str | None = Query(
        None,
        max_length=500,
        description="Case-insensitive match on event name, description, or tags.",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    events, total = await event_service.list_events(
        db,
        page,
        page_size,
        search=search,
        user_email=user.email,
    )
    event_ids = [e.id for e in events]
    liked_ids = await event_like_service.event_ids_liked_by_user(db, user.id, event_ids)
    data = [
        event_service.build_event_list_card(
            e,
            list(e.staging_file_ids or []),
            liked_by_me=(e.id in liked_ids),
        )
        for e in events
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


@router.get("/event/{event_id}", response_model=APIResponse)
async def get_event_for_user(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Active event detail for end users (applicability + full staging media)."""
    user_email = (user.email or "").strip().lower()
    if not user_email:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    today = date.today()
    result = await db.execute(
        select(Event)
        .where(
            Event.id == event_id,
            Event.status == EventStatus.ACTIVE,
            Event.event_start <= today,
            Event.event_end >= today,
            Event.applicability_type == ApplicabilityType.EMPLOYEE,
            Event.applicability_refs.any(user_email),
        )
        .options(selectinload(Event.media_items), selectinload(Event.creator))
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    liked = await event_like_service.is_liked(db, user.id, event_id)
    out = event_service.build_event_out(
        event,
        liked_by_me=liked,
        file_ids=list(event.staging_file_ids or []),
    )
    return APIResponse(message="Event fetched", status_code=200, status="success", data=out)


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
