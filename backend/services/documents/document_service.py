import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import String as SAString, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload

from models.documents.document import (
    ApplicabilityType,
    Document,
    DocumentRevision,
    DocumentStatus,
    DocumentType,
    DOCUMENT_TYPE_LABELS,
    LABEL_TO_DOCUMENT_TYPE,
    ROLE_DOCUMENT_TYPES,
    document_type_to_label,
)
from models.documents.document_file import DocumentFile
from models.events.user import User
from utils.security import CurrentUser
from schemas.documents.document import (
    DocumentHubCategory,
    DocumentHubItem,
    DocumentHubOut,
    DocumentOut,
    DocumentSavePayload,
    DocumentFileSummary,
    LinkedDocumentDetail,
)
from services.documents.document_file_service import (
    upload_document_files,
    validate_file_count,
)
from storage import get_storage
from utils.applicability import validate_applicability_refs

logger = logging.getLogger(__name__)


SINGLE_ACTIVE_DOCUMENT_TYPES = {
    DocumentType.FAQ,
    DocumentType.LATEST_NEWS_AND_ANNOUNCEMENTS,
}



def get_allowed_types_for_user(user: CurrentUser) -> list[DocumentType]:
    allowed: list[DocumentType] = []
    if user.is_policy_hub_admin:
        allowed.extend(ROLE_DOCUMENT_TYPES["policy_hub_admin"])
    if user.is_knowledge_hub_admin:
        allowed.extend(ROLE_DOCUMENT_TYPES["knowledge_hub_admin"])
    if user.is_master_admin:
        allowed = list(DocumentType)
    return allowed


def _check_type_permission(user: CurrentUser, doc_type: DocumentType) -> None:
    allowed = get_allowed_types_for_user(user)
    if doc_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You are not allowed to manage documents of type {doc_type.value}",
        )



async def save_document(
    db: AsyncSession,
    user: CurrentUser,
    payload: DocumentSavePayload,
    *,
    document_id: int | None = None,
    files: list[UploadFile] | None = None,
) -> Document:
    is_new = document_id is None
    _check_type_permission(user, payload.document_type)
    validate_applicability_refs(payload.applicability_type, payload.applicability_refs)

    if is_new:
        doc = Document(created_by=user.id, name=payload.name, document_type=payload.document_type, tags=payload.tags)
        db.add(doc)
        await db.flush()
    else:
        doc = await get_document(db, document_id)
    await _validate_document_save_request(db, payload, doc, is_new=is_new)

    if not is_new:
        if doc.status == DocumentStatus.ACTIVE and payload.status == DocumentStatus.DRAFT:
            doc = await _get_or_create_draft(db, doc, user.id)
        elif doc.status == DocumentStatus.ACTIVE and payload.status == DocumentStatus.ACTIVE:
            if doc.replaces_document_id is None and (not payload.change_remarks or not payload.change_remarks.strip()):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="change_remarks is required when editing a document",
                )

    if payload.linked_document_ids:
        await _validate_linked_ids(db, payload.linked_document_ids, doc.id)

    doc.name = payload.name
    doc.document_type = payload.document_type
    doc.tags = payload.tags
    doc.summary = payload.summary
    doc.legislation_id = payload.legislation_id
    doc.sub_legislation_id = payload.sub_legislation_id
    doc.version = payload.version
    doc.next_review_date = payload.next_review_date
    doc.download_allowed = payload.download_allowed
    doc.linked_document_ids = payload.linked_document_ids or []
    doc.applicability_type = payload.applicability_type
    doc.applicability_refs = payload.applicability_refs
    doc.change_remarks = payload.change_remarks

    uploaded_ids: list[int] = []
    uploaded_names: list[str] = []
    if files:
        uploaded = await upload_document_files(db, doc.id, payload.document_type, files)
        uploaded_ids = [f.id for f in uploaded]
        uploaded_names = [f.original_filename for f in uploaded]

    if payload.selected_filenames is not None:
        all_names = list(dict.fromkeys([*payload.selected_filenames, *uploaded_names]))
        await _sync_staging(db, doc, all_names)
    elif uploaded_ids:
        existing_staging = list(doc.staging_file_ids or [])
        for fid in uploaded_ids:
            if fid not in existing_staging:
                existing_staging.append(fid)
        doc.staging_file_ids = existing_staging

    staging_files = _get_staging_files(doc)
    if payload.status == DocumentStatus.ACTIVE:
        validate_file_count(len(staging_files))
        if doc.document_type in SINGLE_ACTIVE_DOCUMENT_TYPES:
            existing = await _get_active_singleton_document(db, doc.document_type, exclude_id=doc.id)
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Active {doc.document_type.value} already exists",
                )

    if payload.status == DocumentStatus.ACTIVE:
        if doc.replaces_document_id is not None:
            doc = await _publish_draft(db, doc)
        else:
            await _publish_document(db, doc)
    else:
        doc.status = DocumentStatus.DRAFT

    await db.flush()
    await db.refresh(doc)
    return await get_document_for_detail(db, doc.id)



async def get_document(db: AsyncSession, document_id: int) -> Document:
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


async def get_document_for_detail(db: AsyncSession, document_id: int) -> Document:
    """Load document with files and creator for detail/edit responses."""
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.files), selectinload(Document.creator))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


async def get_document_detail_for_revision(db: AsyncSession, document_id: int) -> DocumentOut:
    """Item detail: full Document + User.username only; files filtered by current version."""
    row = await db.execute(
        select(Document, User.username.label("created_by_name"))
        .join(User, Document.created_by == User.staff_id)
        .where(Document.id == document_id)
        .options(selectinload(Document.revisions), selectinload(Document.files))
    )
    one = row.one_or_none()
    if not one:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    doc, created_by_name = one[0], one[1]
    ver = doc.current_media_version

    file_ids = _get_file_ids_for_version_sync(doc, ver)
    file_by_id = {f.id: f for f in doc.files}
    version_files = [file_by_id[fid] for fid in file_ids if fid in file_by_id]

    files = [
        DocumentFileSummary(
            id=f.id,
            original_filename=f.original_filename,
            file_type=f.file_type,
            file_url=f.file_url,
            media_versions=_compute_media_versions(f.id, doc),
            file_size_bytes=f.file_size_bytes,
        )
        for f in version_files
    ]

    linked_details = None
    if doc.linked_document_ids:
        raw = await get_linked_document_details(db, doc.linked_document_ids)
        linked_details = [LinkedDocumentDetail(**r) for r in raw]

    return DocumentOut(
        id=doc.id,
        name=doc.name,
        document_type=document_type_to_label(doc.document_type.value),
        tags=doc.tags,
        summary=doc.summary,
        legislation_id=doc.legislation_id,
        sub_legislation_id=doc.sub_legislation_id,
        next_review_date=doc.next_review_date,
        download_allowed=doc.download_allowed,
        applicability_type=doc.applicability_type,
        applicability_refs=doc.applicability_refs,
        status=doc.status,
        current_media_version=ver,
        current_revision_number=doc.current_revision_number,
        change_remarks=doc.change_remarks,
        deactivate_remarks=doc.deactivate_remarks,
        deactivated_at=doc.deactivated_at,
        replaces_document_id=doc.replaces_document_id,
        created_by=doc.created_by,
        created_by_name=created_by_name,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        files=files,
        linked_document_details=linked_details,
    )


async def list_documents(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status_filter: DocumentStatus | None = None,
    document_type_filter: DocumentType | None = None,
) -> tuple[list[Document], int]:
    query = select(Document)
    count_query = select(func.count()).select_from(Document)

    if status_filter:
        query = query.where(Document.status == status_filter)
        count_query = count_query.where(Document.status == status_filter)

    if document_type_filter:
        query = query.where(Document.document_type == document_type_filter)
        count_query = count_query.where(Document.document_type == document_type_filter)

    total = (await db.execute(count_query)).scalar() or 0
    query = (
        query.options(selectinload(Document.creator))
        .order_by(Document.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    docs = list((await db.execute(query)).scalars().all())
    return docs, total


async def list_active_documents_for_home(
    db: AsyncSession,
    document_type: DocumentType,
    page: int,
    page_size: int,
) -> tuple[list[Document], int]:
    """Active docs of one type with `Document.files` only (no creator, no revisions join)."""
    filters = (
        Document.document_type == document_type,
        Document.status == DocumentStatus.ACTIVE,
    )
    count_query = select(func.count()).select_from(Document).where(*filters)
    total = (await db.execute(count_query)).scalar() or 0
    _home_doc_cols = (
        Document.id,
        Document.name,
        Document.document_type,
        Document.updated_at,
    )
    _home_file_cols = (
        DocumentFile.id,
        DocumentFile.document_id,
        DocumentFile.file_type,
        DocumentFile.file_url,
        DocumentFile.original_filename,
        DocumentFile.sort_order,
    )
    query = (
        select(Document)
        .where(*filters)
        .options(
            load_only(*_home_doc_cols),
            selectinload(Document.files).options(load_only(*_home_file_cols)),
        )
        .order_by(Document.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    docs = list((await db.execute(query)).scalars().all())
    return docs, total


def home_by_type_preview(doc: Document) -> dict:
    """Minimal home/gallery payload: id, name, document_type, files with SAS URLs.

    Uses rows in ``document_files`` for this document, ordered by ``sort_order``.
    No revision table access — suitable for simple home galleries (e.g. Latest News).
    """
    storage = get_storage()
    files_sorted = sorted(doc.files or [], key=lambda f: f.sort_order)
    files_out: list[dict] = []
    for f in files_sorted:
        files_out.append(
            {
                "id": f.id,
                "original_filename": f.original_filename,
                "file_type": f.file_type.value,
                "file_url": storage.get_read_url(f.file_url),
            }
        )
    return {
        "id": doc.id,
        "name": doc.name,
        "document_type": document_type_to_label(doc.document_type.value),
        "files": files_out,
    }


async def toggle_document_status(
    db: AsyncSession,
    document_id: int,
    user: CurrentUser | None = None,
    deactivate_remarks: str | None = None,
) -> Document:
    doc = await get_document(db, document_id)
    _check_type_permission(user, doc.document_type)

    if doc.status == DocumentStatus.ACTIVE:
        if not deactivate_remarks or not deactivate_remarks.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Deactivation remarks are required when deactivating a document",
            )
        doc.status = DocumentStatus.INACTIVE
        doc.deactivate_remarks = deactivate_remarks.strip()
        doc.deactivated_at = func.now()
        doc.deactivated_by = user.id if user else None
    elif doc.status == DocumentStatus.INACTIVE:
        await _validate_active_document_name_uniqueness(
            db,
            name=doc.name,
            document_type=doc.document_type,
            exclude_id=doc.id,
        )
        if doc.document_type in SINGLE_ACTIVE_DOCUMENT_TYPES:
            existing = await _get_active_singleton_document(db, doc.document_type, exclude_id=document_id)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Active {doc.document_type.value} already exists",
                )
        doc.status = DocumentStatus.ACTIVE
        doc.deactivate_remarks = None
        doc.deactivated_at = None
        doc.deactivated_by = None
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only ACTIVE/INACTIVE documents can be toggled",
        )
    await db.flush()
    await db.refresh(doc)
    return doc


async def create_draft_from_document(db: AsyncSession, parent_id: int, user_id: str) -> Document:
    parent = await get_document(db, parent_id)
    if parent.status != DocumentStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only create drafts from active documents",
        )
    draft = await _get_or_create_draft(db, parent, user_id)
    await db.refresh(draft)
    return draft



async def get_linked_options(
    db: AsyncSession,
    document_type: DocumentType,
    exclude_id: int | None = None,
) -> list[dict]:
    if document_type == DocumentType.FAQ:
        return []

    query = (
        select(Document.id, Document.name)
        .where(
            Document.document_type == document_type,
            Document.status == DocumentStatus.ACTIVE,
        )
    )
    if exclude_id is not None:
        query = query.where(Document.id != exclude_id)

    result = await db.execute(query.order_by(Document.name).limit(50))
    return [{"id": row.id, "name": row.name} for row in result.all()]


async def get_linked_document_details(
    db: AsyncSession,
    linked_ids: list[int],
) -> list[dict]:
    """Return id, name, document_type for each linked id (for display)."""
    if not linked_ids:
        return []
    result = await db.execute(
        select(Document.id, Document.name, Document.document_type).where(Document.id.in_(linked_ids))
    )
    return [
        {"id": row.id, "name": row.name, "document_type": document_type_to_label(row.document_type.value)}
        for row in result.all()
    ]


# ── Knowledge Hub ────────────────────────────────────────────────────────

HUB_NEW_DAYS = 2  # Documents created in the last N days are shown as "new"
HUB_MAX_PAGE_SIZE = 100


def _apply_applicability_filter(query, user: CurrentUser, applicability: str | None):
    """Filter hub/list queries by applicability. Uses JSONB @> where possible (GIN-friendly)."""
    if not applicability or applicability.upper() == "ALL":
        return query

    if applicability.upper() == "DIVISION":
        if not user.division_cluster:
            return query.where(Document.applicability_type == ApplicabilityType.ALL)
        div_match = Document.applicability_refs.contains({"divisions": [user.division_cluster]})
        desig_match = Document.applicability_refs.contains({"designations": [user.designation]})
        ref_match = or_(div_match, desig_match)
        return query.where(
            or_(
                Document.applicability_type == ApplicabilityType.ALL,
                (Document.applicability_type == ApplicabilityType.DIVISION) & ref_match,
            )
        )

    if applicability.upper() == "EMPLOYEE":
        # Match user email as a JSON array element (same storage as division list).
        ref_match = Document.applicability_refs.contains([user.email])
        return query.where(
            or_(
                Document.applicability_type == ApplicabilityType.ALL,
                (Document.applicability_type == ApplicabilityType.EMPLOYEE) & ref_match,
            )
        )

    return query


def _apply_search_filter(query, search: str | None):
    if not search:
        return query
    like = f"%{search}%"
    return query.where(
        or_(
            Document.name.ilike(like),
            Document.summary.ilike(like),
            func.cast(Document.tags, SAString).ilike(like),
        )
    )


def _resolve_doc_types(raw: list[str] | None) -> list[DocumentType]:
    if not raw:
        return list(DocumentType)
    result: list[DocumentType] = []
    for dt in raw:
        dt_stripped = dt.strip()
        try:
            result.append(DocumentType(dt_stripped))
            continue
        except ValueError:
            pass
        if dt_stripped in LABEL_TO_DOCUMENT_TYPE:
            result.append(LABEL_TO_DOCUMENT_TYPE[dt_stripped])
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid document type: {dt_stripped}",
            )
    return result


def _hub_ranked_subquery(
    type_enums: list[DocumentType],
    user: CurrentUser,
    applicability: str | None,
    search: str | None,
):
    """Partitioned row numbers per document_type for hub paging (avoids N queries per type)."""
    rn = (
        func.row_number()
        .over(
            partition_by=Document.document_type,
            order_by=Document.updated_at.desc(),
        )
        .label("rn")
    )
    inner = select(
        Document.id,
        Document.name,
        Document.created_at,
        Document.document_type,
        rn,
    ).where(
        Document.status == DocumentStatus.ACTIVE,
        Document.replaces_document_id.is_(None),
        Document.document_type.in_(type_enums),
    )
    inner = _apply_applicability_filter(inner, user, applicability)
    inner = _apply_search_filter(inner, search)
    return inner.subquery("hub_ranked")


async def _hub_counts_by_type(
    db: AsyncSession,
    type_enums: list[DocumentType],
    user: CurrentUser,
    applicability: str | None,
    search: str | None,
    *,
    created_after: datetime | None = None,
) -> dict[DocumentType, int]:
    """Single grouped COUNT per document_type (no subquery wrapper)."""
    stmt = select(Document.document_type, func.count().label("cnt")).where(
        Document.status == DocumentStatus.ACTIVE,
        Document.replaces_document_id.is_(None),
        Document.document_type.in_(type_enums),
    )
    if created_after is not None:
        stmt = stmt.where(Document.created_at >= created_after)
    stmt = _apply_applicability_filter(stmt, user, applicability)
    stmt = _apply_search_filter(stmt, search)
    stmt = stmt.group_by(Document.document_type)
    rows = (await db.execute(stmt)).all()
    return {row[0]: int(row[1]) for row in rows}


async def get_document_hub(
    db: AsyncSession,
    user: CurrentUser,
    *,
    doc_types: list[str] | None = None,
    page: int = 1,
    page_size: int = 10,
    applicability: str | None = None,
    search: str | None = None,
    load_more_type: str | None = None,
    load_more_page: int | None = None,
) -> DocumentHubOut:
    """
    If load_more_type and load_more_page are set, return only that category with
    items for that page (for FE to append). Otherwise return all types with first
    page_size items each (initial load).
    """
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="page must be >= 1",
        )
    if page_size < 1 or page_size > HUB_MAX_PAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"page_size must be between 1 and {HUB_MAX_PAGE_SIZE}",
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=HUB_NEW_DAYS)

    if load_more_type is not None and load_more_page is not None:
        load_more_stripped = load_more_type.strip()
        if not load_more_stripped:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid document type for load more",
            )
        if load_more_page < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="load_more_page must be >= 1",
            )
        doc_type_enum = LABEL_TO_DOCUMENT_TYPE.get(load_more_stripped)
        if doc_type_enum is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid document type for load more: {load_more_type}",
            )
        type_enums = [doc_type_enum]
        is_load_more = True
    else:
        type_enums = _resolve_doc_types(doc_types)
        is_load_more = False

    if not type_enums:
        return DocumentHubOut(categories=[])

    # Two grouped COUNT queries for all types (instead of 2N subquery counts).
    totals = await _hub_counts_by_type(db, type_enums, user, applicability, search)
    new_counts = await _hub_counts_by_type(
        db, type_enums, user, applicability, search, created_after=cutoff
    )

    # One ranked query for hub rows (window over document_type).
    ranked = _hub_ranked_subquery(type_enums, user, applicability, search)
    if is_load_more:
        assert load_more_page is not None
        doc_type_enum = type_enums[0]
        lo = load_more_page
        hi = lo * page_size
        lo_rn = (lo - 1) * page_size
        page_stmt = select(
            ranked.c.id,
            ranked.c.name,
            ranked.c.created_at,
            ranked.c.document_type,
        ).where(
            ranked.c.document_type == doc_type_enum,
            ranked.c.rn > lo_rn,
            ranked.c.rn <= hi,
        )
    else:
        page_stmt = select(
            ranked.c.id,
            ranked.c.name,
            ranked.c.created_at,
            ranked.c.document_type,
        ).where(ranked.c.rn <= page_size)

    page_rows = (await db.execute(page_stmt)).all()

    items_by_type: dict[DocumentType, list[DocumentHubItem]] = defaultdict(list)
    for r in page_rows:
        dt = r.document_type
        items_by_type[dt].append(
            DocumentHubItem(
                id=r.id,
                name=r.name,
                isNew=r.created_at >= cutoff if r.created_at else False,
            )
        )

    categories: list[DocumentHubCategory] = []
    for dt in type_enums:
        total = totals.get(dt, 0)
        new_count = new_counts.get(dt, 0)
        items = items_by_type.get(dt, [])
        if items or (doc_types is not None and doc_types) or (load_more_type is not None):
            categories.append(
                DocumentHubCategory(
                    document_type=DOCUMENT_TYPE_LABELS.get(dt, dt.value),
                    total=total,
                    new_count=new_count,
                    items=items,
                )
            )

    return DocumentHubOut(categories=categories)


async def list_revisions(db: AsyncSession, document_id: int) -> list[DocumentRevision]:
    result = await db.execute(
        select(DocumentRevision)
        .where(DocumentRevision.document_id == document_id)
        .order_by(DocumentRevision.media_version.desc(), DocumentRevision.revision_number.desc())
    )
    revs = list(result.scalars().all())
    if revs:
        return revs
    doc_exists = (
        await db.execute(select(Document.id).where(Document.id == document_id))
    ).scalar_one_or_none()
    if doc_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return []


async def get_revision(
    db: AsyncSession, document_id: int, media_version: int, revision_number: int,
) -> DocumentRevision:
    result = await db.execute(
        select(DocumentRevision)
        .where(
            DocumentRevision.document_id == document_id,
            DocumentRevision.media_version == media_version,
            DocumentRevision.revision_number == revision_number,
        )
        .options(
            selectinload(DocumentRevision.creator),
            selectinload(DocumentRevision.document),
        )
    )
    rev = result.scalar_one_or_none()
    if rev:
        return rev
    await get_document(db, document_id)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found")


def _compute_media_versions(file_id: int, doc: Document) -> list[int]:
    """Compute the media_versions list for a file based on staging and revisions."""
    versions: list[int] = []
    if file_id in (doc.staging_file_ids or []):
        versions.append(0)
    for rev in (doc.revisions or []):
        if file_id in (rev.file_ids or []):
            versions.append(rev.media_version)
    return sorted(set(versions))


def build_document_out(
    doc: Document,
    linked_document_details: list[LinkedDocumentDetail] | None = None,
) -> DocumentOut:
    """Build DocumentOut from loaded Document (with files and creator)."""
    ver = doc.current_media_version
    target_ver = ver if ver > 0 else 0
    target_file_ids = _get_file_ids_for_version_sync(doc, target_ver)
    file_by_id = {f.id: f for f in doc.files}
    files = [
        DocumentFileSummary(
            id=f.id,
            original_filename=f.original_filename,
            file_type=f.file_type,
            file_url=f.file_url,
            media_versions=_compute_media_versions(f.id, doc),
            file_size_bytes=f.file_size_bytes,
        )
        for fid in target_file_ids
        if (f := file_by_id.get(fid)) is not None
    ]
    return DocumentOut(
        id=doc.id,
        name=doc.name,
        document_type=document_type_to_label(doc.document_type.value),
        tags=doc.tags,
        summary=doc.summary,
        legislation_id=doc.legislation_id,
        sub_legislation_id=doc.sub_legislation_id,
        version=doc.version,
        next_review_date=doc.next_review_date,
        download_allowed=doc.download_allowed,
        linked_document_ids=doc.linked_document_ids,
        applicability_type=doc.applicability_type,
        applicability_refs=doc.applicability_refs,
        status=doc.status,
        current_media_version=ver,
        current_revision_number=doc.current_revision_number,
        version_display=f"{ver}.{doc.current_revision_number}",
        change_remarks=doc.change_remarks,
        deactivate_remarks=doc.deactivate_remarks,
        deactivated_at=doc.deactivated_at,
        replaces_document_id=doc.replaces_document_id,
        created_by=doc.created_by,
        created_by_name=doc.creator.username,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        files=files,
        linked_document_details=linked_document_details,
    )


async def get_revision_snapshot(
    db: AsyncSession,
    document_id: int,
    media_version: int,
    revision_number: int,
) -> tuple[DocumentRevision, list[DocumentFile]]:
    """Load document revision and files at that media version."""
    revision = await get_revision(db, document_id, media_version, revision_number)
    all_files = await _get_all_files(db, document_id)
    file_by_id = {f.id: f for f in all_files}
    files = [file_by_id[fid] for fid in (revision.file_ids or []) if fid in file_by_id]
    return revision, files



async def _get_active_faq(db: AsyncSession, exclude_id: int | None = None) -> Document | None:
    return await _get_active_singleton_document(db, DocumentType.FAQ, exclude_id=exclude_id)


async def _get_active_singleton_document(
    db: AsyncSession,
    document_type: DocumentType,
    exclude_id: int | None = None,
) -> Document | None:
    q = select(Document).where(
        Document.document_type == document_type,
        Document.status == DocumentStatus.ACTIVE,
    )
    if exclude_id is not None:
        q = q.where(Document.id != exclude_id)
    result = await db.execute(q.limit(1))
    return result.scalar_one_or_none()


async def _validate_document_save_request(
    db: AsyncSession,
    payload: DocumentSavePayload,
    existing_doc: Document,
    *,
    is_new: bool,
) -> None:
    if payload.document_type == DocumentType.FAQ and payload.linked_document_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="FAQ documents cannot have linked items",
        )

    if not is_new and existing_doc.document_type != payload.document_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="document_type cannot be changed once the document is created",
        )

    if payload.status != DocumentStatus.ACTIVE:
        return

    await _validate_active_document_name_uniqueness(
        db,
        name=payload.name,
        document_type=payload.document_type,
        exclude_id=None if is_new else existing_doc.id,
        allow_replaced_active_id=existing_doc.replaces_document_id,
    )

    if payload.document_type not in SINGLE_ACTIVE_DOCUMENT_TYPES:
        return

    existing = await _get_active_singleton_document(
        db,
        payload.document_type,
        exclude_id=None if is_new else existing_doc.id,
    )
    if existing is None:
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Active {payload.document_type.value} already exists",
    )


async def _validate_active_document_name_uniqueness(
    db: AsyncSession,
    *,
    name: str,
    document_type: DocumentType,
    exclude_id: int | None = None,
    allow_replaced_active_id: int | None = None,
) -> None:
    normalized_name = (name or "").strip().lower()
    stmt = (
        select(Document.id)
        .where(
            Document.status == DocumentStatus.ACTIVE,
            Document.document_type == document_type,
            func.lower(func.trim(Document.name)) == normalized_name,
        )
        .order_by(Document.id.asc())
        .limit(1)
    )
    if exclude_id is not None:
        stmt = stmt.where(Document.id != exclude_id)
    if allow_replaced_active_id is not None:
        stmt = stmt.where(Document.id != allow_replaced_active_id)

    existing_id = (await db.execute(stmt)).scalar_one_or_none()
    if existing_id is None:
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Active document with name '{name}' already exists for "
            f"type '{document_type.value}'"
        ),
    )


async def _validate_linked_ids(
    db: AsyncSession,
    linked_ids: list[int],
    current_id: int,
) -> None:
    if not linked_ids:
        return
    unique_ids = list(dict.fromkeys(linked_ids))
    if len(unique_ids) != len(linked_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate linked document ids are not allowed",
        )
    if len(unique_ids) > 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 6 linked items allowed",
        )
    result = await db.execute(
        select(Document.id, Document.document_type, Document.status)
        .where(Document.id.in_(unique_ids))
    )
    found = {row.id: row for row in result.all()}
    for lid in unique_ids:
        if lid == current_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot link a document to itself",
            )
        if lid not in found:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Linked document {lid} not found",
            )
        row = found[lid]
        if row.status != DocumentStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Linked document {lid} must be active",
            )


async def _get_or_create_draft(db: AsyncSession, parent: Document, user_id: str) -> Document:
    existing = (await db.execute(
        select(Document).where(
            Document.replaces_document_id == parent.id,
            Document.status == DocumentStatus.DRAFT,
        )
    )).scalar_one_or_none()
    if existing:
        return existing

    parent_file_ids = await _get_file_ids_for_version(db, parent, parent.current_media_version)

    parent_files = await _get_all_files(db, parent.id)
    parent_file_by_id = {f.id: f for f in parent_files}

    draft = Document(
        name=parent.name,
        document_type=parent.document_type,
        tags=parent.tags,
        summary=parent.summary,
        legislation_id=parent.legislation_id,
        sub_legislation_id=parent.sub_legislation_id,
        version=parent.version,
        next_review_date=parent.next_review_date,
        download_allowed=parent.download_allowed,
        linked_document_ids=parent.linked_document_ids,
        applicability_type=parent.applicability_type,
        applicability_refs=parent.applicability_refs,
        current_media_version=parent.current_media_version,
        current_revision_number=parent.current_revision_number,
        status=DocumentStatus.DRAFT,
        replaces_document_id=parent.id,
        created_by=user_id,
    )
    db.add(draft)
    await db.flush()

    new_files: list[DocumentFile] = []
    for fid in parent_file_ids:
        pf = parent_file_by_id.get(fid)
        if not pf:
            continue
        new_file = DocumentFile(
            document_id=draft.id,
            file_type=pf.file_type,
            file_url=pf.file_url,
            original_filename=pf.original_filename,
            file_size_bytes=pf.file_size_bytes,
            sort_order=pf.sort_order,
        )
        db.add(new_file)
        new_files.append(new_file)
    await db.flush()
    draft.staging_file_ids = [f.id for f in new_files]
    return draft



async def _publish_document(db: AsyncSession, doc: Document) -> None:
    if doc.current_media_version == 0:
        doc.current_media_version = 1
        doc.current_revision_number = 0
    else:
        if await _version_should_bump(db, doc):
            doc.current_media_version += 1
            doc.current_revision_number = 0
        else:
            doc.current_revision_number += 1

    published_file_ids = list(doc.staging_file_ids or [])

    db.add(DocumentRevision(
        document_id=doc.id,
        media_version=doc.current_media_version,
        revision_number=doc.current_revision_number,
        name=doc.name,
        document_type=doc.document_type,
        tags=doc.tags,
        summary=doc.summary,
        applicability_type=doc.applicability_type,
        applicability_refs=doc.applicability_refs,
        file_ids=published_file_ids,
        created_by=doc.created_by,
    ))

    doc.staging_file_ids = []
    doc.status = DocumentStatus.ACTIVE


async def _publish_draft(db: AsyncSession, draft: Document) -> Document:
    result = await db.execute(
        select(Document)
        .where(Document.id == draft.replaces_document_id)
        .options(selectinload(Document.revisions))
    )
    parent = result.scalar_one_or_none()
    if not parent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent document not found")

    last_rev = _find_latest_revision(parent)
    name_changed = (draft.name != last_rev.name) if last_rev else True
    files_changed = await _files_differ_between(db, draft, 0, parent, parent.current_media_version)

    if name_changed or files_changed:
        draft.current_media_version = parent.current_media_version + 1
        draft.current_revision_number = 0
    else:
        draft.current_media_version = parent.current_media_version
        draft.current_revision_number = parent.current_revision_number + 1

    published_file_ids = list(draft.staging_file_ids or [])

    for rev in parent.revisions:
        rev.document_id = draft.id

    parent_files = await _get_all_files(db, parent.id)
    for f in parent_files:
        f.document_id = draft.id

    db.add(DocumentRevision(
        document_id=draft.id,
        media_version=draft.current_media_version,
        revision_number=draft.current_revision_number,
        name=draft.name,
        document_type=draft.document_type,
        tags=draft.tags,
        summary=draft.summary,
        applicability_type=draft.applicability_type,
        applicability_refs=draft.applicability_refs,
        file_ids=published_file_ids,
        created_by=draft.created_by,
    ))

    parent.status = DocumentStatus.INACTIVE
    draft.status = DocumentStatus.ACTIVE
    draft.replaces_document_id = None
    draft.staging_file_ids = []

    await db.flush()
    await db.refresh(draft)
    return draft



def _find_latest_revision(doc: Document) -> DocumentRevision | None:
    if not doc.revisions:
        return None
    return max(doc.revisions, key=lambda r: (r.media_version, r.revision_number))


async def _version_should_bump(db: AsyncSession, doc: Document) -> bool:
    last_rev = _find_latest_revision(doc)
    if not last_rev:
        return True
    if doc.name != last_rev.name:
        return True
    return await _files_differ_between(db, doc, 0, doc, doc.current_media_version)


async def _get_all_files(db: AsyncSession, document_id: int) -> list[DocumentFile]:
    result = await db.execute(
        select(DocumentFile)
        .where(DocumentFile.document_id == document_id)
        .order_by(DocumentFile.sort_order)
    )
    return list(result.scalars().all())


def _get_staging_files(doc: Document) -> list[int]:
    """Return list of file IDs currently in staging."""
    return list(doc.staging_file_ids or [])


def _get_file_ids_for_version_sync(doc: Document, version: int) -> list[int]:
    """Sync version: get file IDs for a version from loaded doc (staging or revisions)."""
    if version == 0:
        return list(doc.staging_file_ids or [])
    for rev in (doc.revisions or []):
        if rev.media_version == version:
            return list(rev.file_ids or [])
    return list(doc.staging_file_ids or [])


async def _get_file_ids_for_version(db: AsyncSession, doc: Document, version: int) -> list[int]:
    """Get file IDs for a version. For staging (0), use doc.staging_file_ids. For published, find revision."""
    if version == 0:
        return list(doc.staging_file_ids or [])
    result = await db.execute(
        select(DocumentRevision.file_ids)
        .where(
            DocumentRevision.document_id == doc.id,
            DocumentRevision.media_version == version,
        )
        .order_by(DocumentRevision.revision_number.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return list(row)
    return list(doc.staging_file_ids or [])


async def _get_names_for_version(
    db: AsyncSession, doc: Document, version: int,
) -> set[str]:
    file_ids = await _get_file_ids_for_version(db, doc, version)
    if not file_ids:
        return set()
    all_files = await _get_all_files(db, doc.id)
    file_by_id = {f.id: f for f in all_files}
    return {file_by_id[fid].original_filename for fid in file_ids if fid in file_by_id}


async def _files_differ_between(
    db: AsyncSession,
    doc_a: Document, ver_a: int,
    doc_b: Document, ver_b: int,
) -> bool:
    names_a = await _get_names_for_version(db, doc_a, ver_a)
    names_b = await _get_names_for_version(db, doc_b, ver_b)
    return names_a != names_b


async def _sync_staging(
    db: AsyncSession, doc: Document, selected_names: list[str],
) -> None:
    """Make staging match exactly the selected filenames."""
    desired = set(selected_names)
    all_files = await _get_all_files(db, doc.id)
    name_to_file = {f.original_filename: f for f in all_files}
    new_staging: list[int] = []
    for name in selected_names:
        f = name_to_file.get(name)
        if f:
            new_staging.append(f.id)
    doc.staging_file_ids = new_staging
