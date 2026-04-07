"""Home page feeds: what's new + per–document-type gallery (SAS file URLs)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from cache import cache_get, cache_set
from config import settings
from database import get_db
from models.documents.document import DocumentStatus, DocumentType, LABEL_TO_DOCUMENT_TYPE, document_type_to_label
from schemas.events.comman import APIResponse, APIResponsePaginated
from services.documents import document_service
from utils.security import CurrentUser, get_current_user

router = APIRouter()


@router.get("/whats-new", response_model=APIResponsePaginated)
async def whats_new(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Latest updated active documents — id, name, document_type only (no FAQ / Latest News)."""
    # Types omitted from this feed (adjust here if needed).
    skip_types = (DocumentType.FAQ, DocumentType.LATEST_NEWS_AND_ANNOUNCEMENTS)

    cache_key = f"doc:whats_new:{page}:{page_size}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return APIResponsePaginated(
            message="What's new fetched",
            status_code=200,
            status="success",
            data=cached["data"],
            total=cached["total"],
            page=cached["page"],
            page_size=cached["page_size"],
        )

    docs, total = await document_service.list_documents(
        db,
        page,
        page_size,
        status_filter=DocumentStatus.ACTIVE,
        document_type_filter=None,
        exclude_document_types=list(skip_types),
    )
    rows = [
        {
            "id": d.id,
            "name": d.name,
            "document_type": document_type_to_label(d.document_type.value),
        }
        for d in docs
        if d.document_type not in skip_types
    ]
    payload = {"data": rows, "total": total, "page": page, "page_size": page_size}
    await cache_set(cache_key, payload, ttl=settings.ITEM_DETAIL_CACHE_TTL_SECONDS)
    return APIResponsePaginated(
        message="What's new fetched",
        status_code=200,
        status="success",
        data=rows,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/document-gallery", response_model=APIResponse)
async def document_gallery(
    document_type: str = Query(
        ...,
        description="Type label (e.g. 'Latest News and Announcements') or enum value",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Active documents of one type with file SAS URLs — for home carousels / galleries."""
    doc_type_enum = LABEL_TO_DOCUMENT_TYPE.get((document_type or "").strip())
    if doc_type_enum is None:
        try:
            doc_type_enum = DocumentType(document_type.strip())
        except ValueError:
            raise HTTPException(400, detail="Invalid document_type")

    type_key = doc_type_enum.value
    cache_key = f"doc:home_by_type:{type_key}:{page}:{page_size}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return APIResponse(
            message="Document gallery fetched",
            status_code=200,
            status="success",
            data=cached,
        )

    docs, _total = await document_service.list_active_documents_for_home(
        db, doc_type_enum, page, page_size
    )
    out_list = [document_service.home_by_type_preview(d) for d in docs]

    await cache_set(cache_key, out_list, ttl=settings.ITEM_DETAIL_CACHE_TTL_SECONDS)
    return APIResponse(
        message="Document gallery fetched",
        status_code=200,
        status="success",
        data=out_list,
    )
