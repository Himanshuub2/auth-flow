from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.event import EventStatus
from app.models.user import User
from app.schemas.common import APIResponse, APIResponsePaginated
from app.schemas.event import EventSavePayload
from app.services import event_service
from app.utils.security import get_current_user
from app.routers.utils import _to_out, _to_list_out

router = APIRouter()


@router.post("/", response_model=APIResponse, status_code=201)
async def create_event(
    data: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload = EventSavePayload.model_validate_json(data)
    event = await event_service.save_event(db, user.id, payload, files=files or None)
    return APIResponse(
        message="Event created successfully",
        status_code=201,
        status="success",
        data=_to_out(event),
    )


@router.put("/{event_id}", response_model=APIResponse)
async def update_event(
    event_id: int,
    data: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload = EventSavePayload.model_validate_json(data)
    event = await event_service.save_event(
        db, user.id, payload, event_id=event_id, files=files or None
    )
    return APIResponse(
        message="Event updated successfully",
        status_code=200,
        status="success",
        data=_to_out(event),
    )


@router.get("/", response_model=APIResponsePaginated)
async def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: EventStatus | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    events, total = await event_service.list_events(db, page, page_size, status)
    return APIResponsePaginated(
        message="Events fetched successfully",
        status_code=200,
        status="success",
        data=[_to_list_out(e) for e in events],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{event_id}", response_model=APIResponse)
async def get_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = await event_service.get_event(db, event_id)
    return APIResponse(
        message="Event fetched successfully",
        status_code=200,
        status="success",
        data=_to_out(event),
    )


@router.post("/{event_id}/draft", response_model=APIResponse, status_code=201)
async def create_draft_from_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    draft = await event_service.create_draft_from_event(db, event_id, user.id)
    return APIResponse(
        message="Draft created successfully",
        status_code=201,
        status="success",
        data=_to_out(draft),
    )


@router.patch("/{event_id}/toggle-status", response_model=APIResponse)
async def toggle_event_status(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = await event_service.toggle_event_status(db, event_id)
    return APIResponse(
        message="Event status updated successfully",
        status_code=200,
        status="success",
        data=_to_out(event),
    )


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await event_service.delete_event(db, event_id)

