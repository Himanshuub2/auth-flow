import logging

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.documents.document import (
    Document,
    DocumentRevision,
    DocumentStatus,
    DocumentType,
    ROLE_DOCUMENT_TYPES,
    document_type_to_label,
)
from app.models.documents.document_file import DocumentFile
from app.models.events.user import User
from app.schemas.documents.document import (
    DocumentOut,
    DocumentSavePayload,
    DocumentFileSummary,
    LinkedDocumentDetail,
)
from app.services.documents.document_file_service import (
    upload_document_files,
    validate_file_count,
)

logger = logging.getLogger(__name__)



def get_allowed_types_for_user(user: User) -> list[DocumentType]:
    allowed: list[DocumentType] = []
    if user.policy_hub_admin:
        allowed.extend(ROLE_DOCUMENT_TYPES["policy_hub_admin"])
    if user.knowledge_hub_admin:
        allowed.extend(ROLE_DOCUMENT_TYPES["knowledge_hub_admin"])
    if user.is_admin:
        allowed = list(DocumentType)
    return allowed


def _check_type_permission(user: User, doc_type: DocumentType) -> None:
    allowed = get_allowed_types_for_user(user)
    if doc_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You are not allowed to manage documents of type {doc_type.value}",
        )



async def save_document(
    db: AsyncSession,
    user: User,
    payload: DocumentSavePayload,
    *,
    document_id: int | None = None,
    files: list[UploadFile] | None = None,
) -> Document:

    _check_type_permission(user, payload.document_type)

    if payload.document_type == DocumentType.FAQ and payload.linked_document_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="FAQ documents cannot have linked items",
        )

    is_new = document_id is None

    if is_new:
        # FAQ: only one ACTIVE FAQ allowed
        if payload.document_type == DocumentType.FAQ and payload.status == DocumentStatus.ACTIVE:
            existing = await _get_active_faq(db, exclude_id=None)
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Active FAQ already exists",
                )
        doc = Document(created_by=user.id, name=payload.name, document_type=payload.document_type, tags=payload.tags)
        db.add(doc)
        await db.flush()
    else:
        doc = await get_document(db, document_id)

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

    uploaded_names: list[str] = []
    if files:
        uploaded = await upload_document_files(db, doc.id, payload.document_type, files)
        uploaded_names = [f.original_filename for f in uploaded]

    if payload.selected_filenames is not None:
        all_names = list(dict.fromkeys([*payload.selected_filenames, *uploaded_names]))
        await _sync_staging(db, doc, all_names)

    staging_files = await _get_files_for_version(db, doc.id, 0)
    if payload.status == DocumentStatus.ACTIVE:
        validate_file_count(len(staging_files))
        # FAQ: only one ACTIVE FAQ allowed (for update path: activating this doc)
        if doc.document_type == DocumentType.FAQ:
            existing = await _get_active_faq(db, exclude_id=doc.id)
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Active FAQ already exists",
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
    """Item detail: full Document + User.full_name only; files: only required columns (6 < 7)."""
    row = await db.execute(
        select(Document, User.full_name.label("created_by_name"))
        .join(User, Document.created_by == User.id)
        .where(Document.id == document_id)
    )
    one = row.one_or_none()
    if not one:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    doc, created_by_name = one[0], one[1]
    ver = doc.current_media_version
    target_ver = ver if ver > 0 else 0

    file_rows = await db.execute(
        select(
            DocumentFile.id,
            DocumentFile.file_url,
            DocumentFile.original_filename,
            DocumentFile.media_versions,
            DocumentFile.file_type,
            DocumentFile.file_size_bytes,
        )
        .where(
            DocumentFile.document_id == document_id,
            DocumentFile.media_versions.any(target_ver),
        )
        .order_by(DocumentFile.sort_order)
    )
    files = [
        DocumentFileSummary(
            id=r.id,
            original_filename=r.original_filename,
            file_type=r.file_type,
            file_url=r.file_url,
            media_versions=r.media_versions,
            file_size_bytes=r.file_size_bytes,
        )
        for r in file_rows.all()
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


async def deactivate_document(db: AsyncSession, document_id: int, deactivate_remarks: str, deactivated_by: int) -> None:
    doc = await get_document(db, document_id)
    doc.status = DocumentStatus.INACTIVE
    doc.deactivate_remarks = deactivate_remarks
    doc.deactivated_at = func.now()
    doc.deactivated_by = deactivated_by
    await db.flush()


async def toggle_document_status(db: AsyncSession, document_id: int, user: User | None = None) -> Document:
    doc = await get_document(db, document_id)
    _check_type_permission(user, doc.document_type)

    if doc.document_type == DocumentType.FAQ:
        existing = (await db.execute(select(Document)
        .where(
            Document.document_type == DocumentType.FAQ, 
            Document.status == DocumentStatus.ACTIVE,
            Document.id != document_id,
        )
        .limit(1))).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active FAQ already exists")
    if doc.status == DocumentStatus.ACTIVE:
        doc.status = DocumentStatus.INACTIVE
    elif doc.status == DocumentStatus.INACTIVE:
        doc.status = DocumentStatus.ACTIVE
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only ACTIVE/INACTIVE documents can be toggled",
        )
    await db.flush()
    await db.refresh(doc)
    return doc


async def create_draft_from_document(db: AsyncSession, parent_id: int, user_id: int) -> Document:
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



async def list_revisions(db: AsyncSession, document_id: int) -> list[DocumentRevision]:
    await get_document(db, document_id)
    result = await db.execute(
        select(DocumentRevision)
        .where(DocumentRevision.document_id == document_id)
        .order_by(DocumentRevision.media_version.desc(), DocumentRevision.revision_number.desc())
    )
    return list(result.scalars().all())


async def get_revision(
    db: AsyncSession, document_id: int, media_version: int, revision_number: int,
) -> DocumentRevision:
    await get_document(db, document_id)
    result = await db.execute(
        select(DocumentRevision)
        .where(
            DocumentRevision.document_id == document_id,
            DocumentRevision.media_version == media_version,
            DocumentRevision.revision_number == revision_number,
        )
        .options(selectinload(DocumentRevision.creator))
    )
    rev = result.scalar_one_or_none()
    if not rev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found")
    return rev


def build_document_out(
    doc: Document,
    linked_document_details: list[LinkedDocumentDetail] | None = None,
) -> DocumentOut:
    """Build DocumentOut from loaded Document (with files and creator)."""
    ver = doc.current_media_version
    target_ver = ver if ver > 0 else 0
    files = [
        DocumentFileSummary.model_validate(f)
        for f in doc.files
        if target_ver in f.media_versions
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
        created_by_name=doc.creator.full_name,
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
    result = await db.execute(
        select(DocumentFile)
        .where(
            DocumentFile.document_id == document_id,
            DocumentFile.media_versions.any(media_version),
        )
        .order_by(DocumentFile.sort_order)
    )
    files = list(result.scalars().all())
    return revision, files



async def _get_active_faq(db: AsyncSession, exclude_id: int | None = None) -> Document | None:
    """Return the active FAQ document if any. Optionally exclude a document id (e.g. current doc being activated)."""
    q = select(Document).where(
        Document.document_type == DocumentType.FAQ,
        Document.status == DocumentStatus.ACTIVE,
    )
    if exclude_id is not None:
        q = q.where(Document.id != exclude_id)
    result = await db.execute(q.limit(1))
    return result.scalar_one_or_none()


async def _validate_linked_ids(
    db: AsyncSession,
    linked_ids: list[int],
    current_id: int,
) -> None:
    """Validate linked document ids: max 6, no self, must exist and be published/active. Any document type allowed."""
    if not linked_ids:
        return
    if len(linked_ids) > 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 6 linked items allowed",
        )
    result = await db.execute(
        select(Document.id, Document.document_type, Document.status)
        .where(Document.id.in_(linked_ids))
    )
    found = {row.id: row for row in result.all()}
    for lid in linked_ids:
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


async def _get_or_create_draft(db: AsyncSession, parent: Document, user_id: int) -> Document:
    existing = (await db.execute(
        select(Document).where(
            Document.replaces_document_id == parent.id,
            Document.status == DocumentStatus.DRAFT,
        )
    )).scalar_one_or_none()
    if existing:
        return existing

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

    parent_files = await _get_files_for_version(db, parent.id, parent.current_media_version)
    for f in parent_files:
        db.add(DocumentFile(
            document_id=draft.id,
            media_versions=[0],
            file_type=f.file_type,
            file_url=f.file_url,
            original_filename=f.original_filename,
            file_size_bytes=f.file_size_bytes,
            sort_order=f.sort_order,
        ))
    await db.flush()
    return draft



async def _publish_document(db: AsyncSession, doc: Document) -> None:
    if doc.current_media_version == 0:
        doc.current_media_version = 1
        doc.current_revision_number = 0
        new_ver = 1
    else:
        if await _version_should_bump(db, doc):
            doc.current_media_version += 1
            doc.current_revision_number = 0
        else:
            doc.current_revision_number += 1
        new_ver = doc.current_media_version

    staging = await _get_files_for_version(db, doc.id, 0)
    for f in staging:
        clean = [v for v in f.media_versions if v != 0]
        if new_ver not in clean:
            clean.append(new_ver)
        f.media_versions = clean

    all_files = (await db.execute(
        select(DocumentFile).where(DocumentFile.document_id == doc.id)
    )).scalars().all()
    staging_ids = {f.id for f in staging}
    for f in all_files:
        if f.id not in staging_ids and 0 in f.media_versions:
            f.media_versions = [v for v in f.media_versions if v != 0]

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
        created_by=doc.created_by,
    ))
    doc.status = DocumentStatus.ACTIVE


async def _publish_draft(db: AsyncSession, draft: Document) -> Document:
    # Load parent with revisions (like events) so we can move revisions to draft and set parent INACTIVE
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
    files_changed = await _files_differ_between(
        db, draft.id, 0, parent.id, parent.current_media_version,
    )

    if name_changed or files_changed:
        draft.current_media_version = parent.current_media_version + 1
        draft.current_revision_number = 0
    else:
        draft.current_media_version = parent.current_media_version
        draft.current_revision_number = parent.current_revision_number + 1

    new_ver = draft.current_media_version

    staging = await _get_files_for_version(db, draft.id, 0)
    for f in staging:
        clean = [v for v in f.media_versions if v != 0]
        if new_ver not in clean:
            clean.append(new_ver)
        f.media_versions = clean

    for rev in parent.revisions:
        rev.document_id = draft.id

    parent_files = (await db.execute(
        select(DocumentFile).where(DocumentFile.document_id == parent.id)
    )).scalars().all()
    for f in parent_files:
        f.document_id = draft.id

    db.add(DocumentRevision(
        document_id=draft.id,
        media_version=new_ver,
        revision_number=draft.current_revision_number,
        name=draft.name,
        document_type=draft.document_type,
        tags=draft.tags,
        summary=draft.summary,
        applicability_type=draft.applicability_type,
        applicability_refs=draft.applicability_refs,
        created_by=draft.created_by,
    ))

    parent.status = DocumentStatus.INACTIVE
    draft.status = DocumentStatus.ACTIVE
    draft.replaces_document_id = None

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
    return await _files_differ_between(db, doc.id, 0, doc.id, doc.current_media_version)


async def _get_files_for_version(
    db: AsyncSession, document_id: int, version: int,
) -> list[DocumentFile]:
    result = await db.execute(
        select(DocumentFile).where(
            DocumentFile.document_id == document_id,
            DocumentFile.media_versions.any(version),
        ).order_by(DocumentFile.sort_order)
    )
    return list(result.scalars().all())


async def _get_names_for_version(
    db: AsyncSession, document_id: int, version: int,
) -> set[str]:
    result = await db.execute(
        select(DocumentFile.original_filename).where(
            DocumentFile.document_id == document_id,
            DocumentFile.media_versions.any(version),
        )
    )
    return set(result.scalars().all())


async def _files_differ_between(
    db: AsyncSession,
    doc_id_a: int, ver_a: int,
    doc_id_b: int, ver_b: int,
) -> bool:
    names_a = await _get_names_for_version(db, doc_id_a, ver_a)
    names_b = await _get_names_for_version(db, doc_id_b, ver_b)
    return names_a != names_b


async def _sync_staging(
    db: AsyncSession, doc: Document, selected_names: list[str],
) -> None:
    desired = set(selected_names)

    all_files = (await db.execute(
        select(DocumentFile).where(DocumentFile.document_id == doc.id)
    )).scalars().all()

    for f in all_files:
        in_staging = 0 in f.media_versions
        wanted = f.original_filename in desired

        if wanted and not in_staging:
            f.media_versions = [*f.media_versions, 0]
        elif not wanted and in_staging:
            f.media_versions = [v for v in f.media_versions if v != 0]
