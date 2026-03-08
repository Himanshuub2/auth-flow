"""Combined events + documents: list, detail, revisions, snapshot. Router only delegates to items_service."""

import logging

from fastapi import APIRouter, Depends, Query

from app.constants import DOCUMENT, EVENT
from app.database import get_db
from app.schemas.events.comman import APIResponse, APIResponsePaginated
from app.services import items_service
from app.utils.security import get_current_user
from app.models.events.user import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=APIResponsePaginated)
async def list_combined(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    item_type: str | None = Query(None, description=f"Filter by '{EVENT}' or '{DOCUMENT}'"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List events and/or documents with pagination."""
    data, total = await items_service.list_combined(db, page=page, page_size=page_size, item_type=item_type)
    logger.info("list_combined total=%s page=%s", total, page)
    return APIResponsePaginated(
        message="Items fetched",
        status_code=200,
        status="success",
        data=data,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{item_id}", response_model=APIResponse)
async def get_item_detail(
    item_id: int,
    item_type: str = Query(..., description=f"'{EVENT}' or '{DOCUMENT}'"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Fetch full detail for one event or document."""
    data = await items_service.get_item_detail(db, item_id=item_id, item_type=item_type)
    logger.info("get_item_detail item_id=%s item_type=%s", item_id, item_type)
    return APIResponse(message="Item fetched", status_code=200, status="success", data=data)


@router.get("/{item_id}/revisions", response_model=APIResponse)
async def list_item_revisions(
    item_id: int,
    item_type: str = Query(..., description=f"'{EVENT}' or '{DOCUMENT}'"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List revisions for an event or document."""
    data = await items_service.list_item_revisions(db, item_id=item_id, item_type=item_type)
    logger.info("list_item_revisions item_id=%s item_type=%s count=%s", item_id, item_type, len(data))
    return APIResponse(message="Revisions fetched", status_code=200, status="success", data=data)


@router.get("/{item_id}/revisions/{media_version}/{revision_number}", response_model=APIResponse)
async def get_item_revision_snapshot(
    item_id: int,
    media_version: int,
    revision_number: int,
    item_type: str = Query(..., description=f"'{EVENT}' or '{DOCUMENT}'"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get one revision snapshot for an event or document."""
    data = await items_service.get_item_revision_snapshot(
        db, item_id=item_id, item_type=item_type,
        media_version=media_version, revision_number=revision_number,
    )
    logger.info(
        "get_item_revision_snapshot item_id=%s item_type=%s mv=%s rn=%s",
        item_id, item_type, media_version, revision_number,
    )
    return APIResponse(message="Revision fetched", status_code=200, status="success", data=data)
