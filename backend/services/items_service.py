"""
Combined items (events + documents): list, detail, revisions, snapshot.
All logic lives here; routers only call this and return responses.
"""

import logging
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select, func, union_all, literal, String
from sqlalchemy.ext.asyncio import AsyncSession

from cache import cache_get, cache_set
from config import settings
from constants import DOCUMENT, EVENT
from models.documents.document import (
    Document,
    DocumentStatus,
    DocumentType,
    document_type_to_label,
    DOCUMENT_TYPE_LABELS,
    LABEL_TO_DOCUMENT_TYPE,
)
from models.events.event import Event, EventStatus
from models.events.user import User
from schemas.documents.combined import CombinedItemOut, ItemRevisionListItemOut
from schemas.documents.items_filter import ItemsKpiOut
from schemas.documents.document import (
    DocumentOut,
    DocumentRevisionDetailOut,
    DocumentRevisionOut,
    DocumentFileSummary,
    LinkedDocumentDetail,
)
from schemas.events.event import EventOut, RevisionOut
from schemas.events.event_revision import RevisionDetailOut
from schemas.events.event_media import MediaItemOut
from services.documents import document_service
from services.events import event_service, revision_service
from storage import get_storage
from utils import cache_keys

logger = logging.getLogger(__name__)

ITEM_DETAIL_CACHE_TTL = getattr(
    settings, "ITEM_DETAIL_CACHE_TTL_SECONDS", 300
)


async def list_combined(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    item_type: str | None = None,
) -> tuple[list[CombinedItemOut], int]:
    """Paginated combined list of events and/or documents."""
    logger.debug("list_combined page=%s page_size=%s item_type=%s", page, page_size, item_type)

    event_q = (
        select(
            Event.id.label("id"),
            literal(EVENT).label("item_type"),
            Event.event_name.label("name"),
            literal(None).label("document_type"),
            (Event.current_media_version.cast(String) + literal(".") + Event.current_revision_number.cast(String)).label("version_display"),
            Event.status.cast(String).label("status"),
            Event.created_by.label("created_by"),
            Event.created_at.label("created_at"),
            Event.updated_at.label("updated_at"),
            Event.deactivated_by.label("deactivated_by"),
            Event.deactivated_at.label("deactivated_at"),
            literal(None).label("next_review_date"),
            Event.current_revision_number.label("revision"),
            Event.current_media_version.label("version"),
        )
    )
    doc_q = (
        select(
            Document.id.label("id"),
            literal(DOCUMENT).label("item_type"),
            Document.name.label("name"),
            Document.document_type.cast(String).label("document_type"),
            (Document.current_media_version.cast(String) + literal(".") + Document.current_revision_number.cast(String)).label("version_display"),
            Document.status.cast(String).label("status"),
            Document.created_by.label("created_by"),
            Document.created_at.label("created_at"),
            Document.updated_at.label("updated_at"),
            Document.deactivated_by.label("deactivated_by"),
            Document.deactivated_at.label("deactivated_at"),
            Document.next_review_date.label("next_review_date"),
            Document.current_revision_number.label("revision"),
            Document.version.label("version"),
        )
    )
    if item_type == EVENT:
        combined = event_q.subquery()
    elif item_type == DOCUMENT:
        combined = doc_q.subquery()
    else:
        combined = union_all(event_q, doc_q).subquery()

    count_q = select(func.count()).select_from(combined)
    total = (await db.execute(count_q)).scalar() or 0

    rows_q = (
        select(combined)
        .order_by(combined.c.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(rows_q)).all()

    creator_ids = {r.created_by for r in rows} | {r.deactivated_by for r in rows if r.deactivated_by is not None}
    name_map: dict[str, str] = {}
    if creator_ids:
        user_rows = (await db.execute(
            select(User.staff_id, User.username).where(User.staff_id.in_(creator_ids))
        )).all()
        name_map = {u.staff_id: u.username for u in user_rows}

    data = [
        CombinedItemOut(
            id=r.id,
            name=r.name,
            document_type=EVENT if r.item_type == EVENT else (document_type_to_label(r.document_type) or str(r.document_type)),
            version_display=r.version_display,
            status=r.status,
            created_by=r.created_by,
            created_by_name=name_map.get(r.created_by, "Unknown"),
            created_at=r.created_at,
            updated_at=r.updated_at,
            deactivated_by=r.deactivated_by,
            deactivated_by_name=name_map.get(r.deactivated_by) if r.deactivated_by else None,
            deactivated_at=r.deactivated_at,
            next_review_date=r.next_review_date,
            revision=r.revision,
            version=r.version,
        )
        for r in rows
    ]
    logger.debug("list_combined total=%s returned=%s", total, len(data))
    return data, total


def _resolve_document_types(
    document_types: list[str] | None,
) -> tuple[list[DocumentType] | None, bool]:
    """
    Resolve document_types from query (labels or enum values) to doc enums and whether to include events.
    Returns (list of DocumentType for documents, include_events).
    """
    if not document_types:
        return None, True  # no filter: all doc types and events
    doc_enums: list[DocumentType] = []
    include_events = False
    for t in document_types:
        s = (t or "").strip()
        if not s:
            continue
        if s.lower() == EVENT:
            include_events = True
            continue
        if s in LABEL_TO_DOCUMENT_TYPE:
            doc_enums.append(LABEL_TO_DOCUMENT_TYPE[s])
        else:
            try:
                doc_enums.append(DocumentType(s))
            except ValueError:
                pass
    # Return [] for doc_enums when only "event" selected, so document query returns 0 rows
    return (doc_enums, include_events)


async def get_items_kpi(db: AsyncSession) -> ItemsKpiOut:
    """
    KPI counts: active, draft, by_type; and for documents (next_review_date):
    - overdue: next_review_date < today
    - due_for_review: next_review_date >= today
    """
    cached = await cache_get("items:kpi")
    if cached is not None:
        return ItemsKpiOut.model_validate(cached)

    today = date.today()

    _status = lambda s: getattr(s, "value", s)

    # Documents: status counts via GROUP BY
    doc_status_q = (
        select(Document.status, func.count().label("cnt"))
        .select_from(Document)
        .group_by(Document.status)
    )
    doc_status_rows = (await db.execute(doc_status_q)).all()
    doc_active = doc_draft = doc_inactive = 0
    for r in doc_status_rows:
        st = _status(r.status)
        c = r.cnt
        if st == "ACTIVE":
            doc_active = c
        elif st == "DRAFT":
            doc_draft = c
        else:
            doc_inactive += c

    # Documents: count by document_type
    doc_type_q = (
        select(Document.document_type, func.count().label("cnt"))
        .select_from(Document)
        .group_by(Document.document_type)
    )
    doc_type_rows = (await db.execute(doc_type_q)).all()
    by_type: dict[str, int] = {label: 0 for label in DOCUMENT_TYPE_LABELS.values()}
    for r in doc_type_rows:
        dt = r.document_type
        label = document_type_to_label(dt.value if hasattr(dt, "value") else dt)
        if label:
            by_type[label] = r.cnt

    # Documents: overdue (next_review_date < today) and due for review (next_review_date >= today)
    doc_overdue_q = select(func.count()).select_from(Document).where(Document.next_review_date < today)
    doc_due_q = select(func.count()).select_from(Document).where(Document.next_review_date >= today)
    doc_overdue = (await db.execute(doc_overdue_q)).scalar() or 0
    doc_due = (await db.execute(doc_due_q)).scalar() or 0

    # Events: status counts and total
    event_status_q = (
        select(Event.status, func.count().label("cnt"))
        .select_from(Event)
        .group_by(Event.status)
    )
    event_status_rows = (await db.execute(event_status_q)).all()
    event_active = event_draft = event_inactive = 0
    event_total = 0
    for r in event_status_rows:
        st = _status(r.status)
        c = r.cnt
        event_total += c
        if st == "ACTIVE":
            event_active = c
        elif st == "DRAFT":
            event_draft = c
        else:
            event_inactive += c

    result = ItemsKpiOut(
        active_doc=doc_active + event_active,
        due_for_review=doc_due,
        overdue=doc_overdue,
        draft=doc_draft + event_draft,
        by_type={
            **by_type,
            "Event": event_total,
        },
    )
    await cache_set("items:kpi", result.model_dump(mode="json"), ttl=ITEM_DETAIL_CACHE_TTL)
    return result


async def list_combined_filtered(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    item_type: str | None = None,
    document_types: list[str] | None = None,
    document_names: list[str] | None = None,
    statuses: list[str] | None = None,
    last_updated_start: date | None = None,
    last_updated_end: date | None = None,
    next_review_start: date | None = None,
    next_review_end: date | None = None,
    search: str | None = None,
) -> tuple[list[CombinedItemOut], int]:
    """
    Paginated combined list with filters.
    document_types: include only these types (AND); use "event" for events. Multiple = include any of them.
    document_names: include only these names (exact match, multiple).
    statuses: filter by status (DRAFT, ACTIVE, INACTIVE).
    search: ILIKE on document/event name (applied in same API).
    """
    cache_key = cache_keys.items_list(
        page=page,
        page_size=page_size,
        item_type=item_type,
        document_types=document_types,
        document_names=document_names,
        statuses=statuses,
        last_updated_start=last_updated_start,
        last_updated_end=last_updated_end,
        next_review_start=next_review_start,
        next_review_end=next_review_end,
        search=search,
    )
    cached = await cache_get(cache_key)
    if cached is not None:
        return [CombinedItemOut.model_validate(item) for item in cached["data"]], cached["total"]

    doc_enum_list, include_events = _resolve_document_types(document_types)

    event_q = (
        select(
            Event.id.label("id"),
            literal(EVENT).label("item_type"),
            Event.event_name.label("name"),
            literal(None).label("document_type"),
            (Event.current_media_version.cast(String) + literal(".") + Event.current_revision_number.cast(String)).label("version_display"),
            Event.status.cast(String).label("status"),
            Event.created_by.label("created_by"),
            Event.created_at.label("created_at"),
            Event.updated_at.label("updated_at"),
            Event.deactivated_by.label("deactivated_by"),
            Event.deactivated_at.label("deactivated_at"),
            literal(None).label("next_review_date"),
            Event.current_revision_number.label("revision"),
            Event.current_media_version.label("version"),
        )
        .select_from(Event)
    )
    if not include_events and doc_enum_list is not None:
        event_q = event_q.where(literal(False))  # exclude events
    else:
        if document_names:
            event_q = event_q.where(Event.event_name.in_(document_names))
        if statuses:
            valid = [EventStatus(s) for s in statuses if s in ("DRAFT", "ACTIVE", "INACTIVE")]
            if valid:
                event_q = event_q.where(Event.status.in_(valid))
        if last_updated_start is not None:
            event_q = event_q.where(Event.updated_at >= last_updated_start)
        if last_updated_end is not None:
            event_q = event_q.where(Event.updated_at <= last_updated_end)
        if search and search.strip():
            event_q = event_q.where(Event.event_name.ilike(f"%{search.strip()}%"))

    doc_q = (
        select(
            Document.id.label("id"),
            literal(DOCUMENT).label("item_type"),
            Document.name.label("name"),
            Document.document_type.cast(String).label("document_type"),
            (Document.current_media_version.cast(String) + literal(".") + Document.current_revision_number.cast(String)).label("version_display"),
            Document.status.cast(String).label("status"),
            Document.created_by.label("created_by"),
            Document.created_at.label("created_at"),
            Document.updated_at.label("updated_at"),
            Document.deactivated_by.label("deactivated_by"),
            Document.deactivated_at.label("deactivated_at"),
            Document.next_review_date.label("next_review_date"),
            Document.current_revision_number.label("revision"),
            Document.version.label("version"),
        )
        .select_from(Document)
    )
    if doc_enum_list is not None:
        if not doc_enum_list:
            doc_q = doc_q.where(literal(False))
        else:
            doc_q = doc_q.where(Document.document_type.in_(doc_enum_list))
    if document_names:
        doc_q = doc_q.where(Document.name.in_(document_names))
    if statuses:
        valid = [DocumentStatus(s) for s in statuses if s in ("DRAFT", "ACTIVE", "INACTIVE")]
        if valid:
            doc_q = doc_q.where(Document.status.in_(valid))
    if last_updated_start is not None:
        doc_q = doc_q.where(Document.updated_at >= last_updated_start)
    if last_updated_end is not None:
        doc_q = doc_q.where(Document.updated_at <= last_updated_end)
    if next_review_start is not None:
        doc_q = doc_q.where(Document.next_review_date >= next_review_start)
    if next_review_end is not None:
        doc_q = doc_q.where(Document.next_review_date <= next_review_end)
    if search and search.strip():
        doc_q = doc_q.where(Document.name.ilike(f"%{search.strip()}%"))

    if item_type == EVENT:
        combined = event_q.subquery()
    elif item_type == DOCUMENT:
        combined = doc_q.subquery()
    else:
        combined = union_all(event_q, doc_q).subquery()

    count_q = select(func.count()).select_from(combined)
    total = (await db.execute(count_q)).scalar() or 0

    rows_q = (
        select(combined)
        .order_by(combined.c.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(rows_q)).all()

    creator_ids = {r.created_by for r in rows} | {r.deactivated_by for r in rows if r.deactivated_by is not None}
    name_map: dict[str, str] = {}
    if creator_ids:
        user_rows = (await db.execute(
            select(User.staff_id, User.username).where(User.staff_id.in_(creator_ids))
        )).all()
        name_map = {u.staff_id: u.username for u in user_rows}

    data = [
        CombinedItemOut(
            id=r.id,
            name=r.name,
            document_type=EVENT if r.item_type == EVENT else (document_type_to_label(r.document_type) or str(r.document_type)),
            version_display=r.version_display,
            status=r.status,
            created_by=r.created_by,
            created_by_name=name_map.get(r.created_by, "Unknown"),
            created_at=r.created_at,
            updated_at=r.updated_at,
            deactivated_by=r.deactivated_by,
            deactivated_by_name=name_map.get(r.deactivated_by) if r.deactivated_by else None,
            deactivated_at=r.deactivated_at,
            next_review_date=r.next_review_date,
            revision=r.revision,
            version=r.version,
        )
        for r in rows
    ]
    await cache_set(
        cache_key,
        {
            "total": total,
            "data": [item.model_dump(mode="json") for item in data],
        },
        ttl=ITEM_DETAIL_CACHE_TTL,
    )
    return data, total


async def get_item_detail(
    db: AsyncSession,
    item_id: int,
    item_type: str,
) -> EventOut | DocumentOut:
    """Load full detail for one event or document. Uses Redis cache with short TTL."""
    cache_key = cache_keys.item_detail(item_type, item_id)
    cached = await cache_get(cache_key)
    if cached is not None:
        logger.debug("get_item_detail cache hit key=%s", cache_key)
        return EventOut.model_validate(cached) if item_type == EVENT else DocumentOut.model_validate(cached)

    logger.debug("get_item_detail item_id=%s item_type=%s", item_id, item_type)
    if item_type == EVENT:
        data = await event_service.get_event_detail_for_revision(db, item_id)
    elif item_type == DOCUMENT:
        data = await document_service.get_document_detail_for_revision(db, item_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"item_type must be '{EVENT}' or '{DOCUMENT}'",
        )
    await cache_set(cache_key, data.model_dump(mode="json"), ttl=ITEM_DETAIL_CACHE_TTL)
    return data


async def list_item_revisions(
    db: AsyncSession,
    item_id: int,
    item_type: str,
) -> list[ItemRevisionListItemOut]:
    """List revisions for an event or document."""
    logger.debug("list_item_revisions item_id=%s item_type=%s", item_id, item_type)

    if item_type == EVENT:
        rows = await revision_service.list_revisions(db, item_id)
        return [
            ItemRevisionListItemOut(
                id=r.id,
                media_version=r.media_version,
                revision_number=r.revision_number,
                version_display=f"{r.media_version}.{r.revision_number}",
                created_at=r.created_at,
                change_remarks=getattr(r, "change_remarks", None),
                event_id=r.event_id,
                document_id=None,
            )
            for r in rows
        ]
    if item_type == DOCUMENT:
        revs = await document_service.list_revisions(db, item_id)
        return [
            ItemRevisionListItemOut(
                id=r.id,
                media_version=r.media_version,
                revision_number=r.revision_number,
                version_display=f"{r.media_version}.{r.revision_number}",
                created_at=r.created_at,
                change_remarks=None,
                event_id=None,
                document_id=r.document_id,
            )
            for r in revs
        ]
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"item_type must be '{EVENT}' or '{DOCUMENT}'",
    )


async def get_item_revision_snapshot(
    db: AsyncSession,
    item_id: int,
    item_type: str,
    media_version: int,
    revision_number: int,
) -> RevisionDetailOut | DocumentRevisionDetailOut:
    """Load one revision snapshot for an event or document."""
    logger.debug(
        "get_item_revision_snapshot item_id=%s item_type=%s mv=%s rn=%s",
        item_id, item_type, media_version, revision_number,
    )

    if item_type == EVENT:
        revision, media_items = await revision_service.get_revision_snapshot(
            db, item_id, media_version, revision_number
        )
        event = revision.event
        rev_out = RevisionOut(
            id=revision.id,
            event_id=revision.event_id,
            media_version=revision.media_version,
            revision_number=revision.revision_number,
            version_display=f"{revision.media_version}.{revision.revision_number}",
            event_name=revision.event_name,
            sub_event_name=revision.sub_event_name,
            event_dates=revision.event_dates,
            description=revision.description,
            tags=revision.tags,
            change_remarks=revision.change_remarks,
            deactivate_remarks=event.deactivate_remarks,
            status=event.status.value,
            updated_at=event.updated_at,
            created_by=revision.created_by,
            created_by_name=revision.creator.username,
            created_at=revision.created_at,
        )
        storage = get_storage()
        return RevisionDetailOut(
            revision=rev_out,
            media_items=[
                MediaItemOut(
                    id=m.id,
                    event_id=m.event_id,
                    media_versions=[media_version],
                    file_type=m.file_type,
                    file_url=storage.get_read_url(m.file_url),
                    blob_path=m.file_url,
                    thumbnail_url=storage.get_read_url(m.thumbnail_url) if m.thumbnail_url else None,
                    thumbnail_blob_path=m.thumbnail_url,
                    caption=m.caption,
                    description=m.description,
                    sort_order=m.sort_order,
                    file_size_bytes=m.file_size_bytes,
                    original_filename=m.original_filename,
                    created_at=m.created_at,
                )
                for m in media_items
            ],
        )
    if item_type == "document":
        revision, files = await document_service.get_revision_snapshot(
            db, item_id, media_version, revision_number
        )
        doc = revision.document
        rev_out = DocumentRevisionOut(
            id=revision.id,
            document_id=revision.document_id,
            media_version=revision.media_version,
            revision_number=revision.revision_number,
            version_display=f"{revision.media_version}.{revision.revision_number}",
            name=revision.name,
            document_type=document_type_to_label(revision.document_type.value),
            tags=revision.tags,
            summary=revision.summary,
            applicability_type=revision.applicability_type,
            applicability_refs=revision.applicability_refs,
            change_remarks=doc.change_remarks,
            deactivate_remarks=doc.deactivate_remarks,
            status=doc.status.value,
            updated_at=doc.updated_at,
            created_by=revision.created_by,
            created_by_name=revision.creator.username,
            created_at=revision.created_at,
        )
        return DocumentRevisionDetailOut(
            revision=rev_out,
            files=[
                DocumentFileSummary(
                    id=f.id,
                    original_filename=f.original_filename,
                    file_type=f.file_type,
                    file_url=f.file_url,
                    media_versions=[media_version],
                    file_size_bytes=f.file_size_bytes,
                )
                for f in files
            ],
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"item_type must be '{EVENT}' or '{DOCUMENT}'",
    )
