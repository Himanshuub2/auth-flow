"""Combined events + documents: list, detail, revisions, snapshot, KPI, filter."""

import logging

from fastapi import APIRouter, Body, Depends, Query

from constants import DOCUMENT, EVENT
from database import get_db
from schemas.documents.items_filter import ItemsListBody
from schemas.events.comman import APIResponse, APIResponsePaginated
from services import items_service
from utils.security import CurrentUser, get_current_user
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/kpi", response_model=APIResponse)
async def get_items_kpi(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """KPI: active, due for review (next_review_date >= today), overdue (next_review_date < today), draft, and by type."""
    data = await items_service.get_items_kpi(db)
    return APIResponse(message="KPI fetched", status_code=200, status="success", data=data)


@router.post("/", response_model=APIResponsePaginated)
async def list_combined(
    body: ItemsListBody | None = Body(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Paginated list of events and/or documents. All filters and pagination in payload (optional; empty body = defaults)."""
    payload = body or ItemsListBody()
    data, total = await items_service.list_combined_filtered(
        db,
        page=payload.page,
        page_size=payload.page_size,
        item_type=payload.item_type,
        document_types=payload.document_types,
        document_names=payload.document_names,
        statuses=payload.statuses,
        last_updated_start=payload.last_updated_start,
        last_updated_end=payload.last_updated_end,
        next_review_start=payload.next_review_start,
        next_review_end=payload.next_review_end,
        search=payload.search,
    )
    logger.info("list_combined total=%s page=%s", total, payload.page)
    return APIResponsePaginated(
        message="Items fetched",
        status_code=200,
        status="success",
        data=data,
        total=total,
        page=payload.page,
        page_size=payload.page_size,
    )


@router.get("/{item_id}", response_model=APIResponse)
async def get_item_detail(
    item_id: int,
    item_type: str = Query(..., description=f"'{EVENT}' or '{DOCUMENT}'"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    data = await items_service.get_item_detail(db, item_id=item_id, item_type=item_type)
    logger.info("get_item_detail item_id=%s item_type=%s", item_id, item_type)
    return APIResponse(message="Item fetched", status_code=200, status="success", data=data)


@router.get("/{item_id}/revisions", response_model=APIResponse)
async def list_item_revisions(
    item_id: int,
    item_type: str = Query(..., description=f"'{EVENT}' or '{DOCUMENT}'"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
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
    user: CurrentUser = Depends(get_current_user),
):
    data = await items_service.get_item_revision_snapshot(
        db, item_id=item_id, item_type=item_type,
        media_version=media_version, revision_number=revision_number,
    )
    logger.info(
        "get_item_revision_snapshot item_id=%s item_type=%s mv=%s rn=%s",
        item_id, item_type, media_version, revision_number,
    )
    return APIResponse(message="Revision fetched", status_code=200, status="success", data=data)
