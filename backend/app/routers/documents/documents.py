from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_delete, cache_get, cache_set
from app.config import settings
from app.database import get_db
from app.models.documents.document import Document, DocumentStatus, DocumentType, LABEL_TO_DOCUMENT_TYPE, document_type_to_label
from app.models.events.user import User
from app.schemas.documents.document import (
    DeactivatePayload,
    DocumentHubOut,
    DocumentOut,
    DocumentRevisionOut,
    DocumentSavePayload,
    LinkedDocumentDetail,
    RevisionListItemOut,
)
from app.schemas.documents.reference import LinkedOptionOut
from app.schemas.events.comman import APIResponse, APIResponsePaginated
from app.services.documents import document_service
from app.utils.security import get_current_user

router = APIRouter()


def _to_out(
    doc: Document,
    linked_document_details: list[LinkedDocumentDetail] | None = None,
) -> DocumentOut:
    from app.services.documents.document_service import build_document_out
    return build_document_out(doc, linked_document_details)


def _to_list_out(doc: Document) -> DocumentOut:
    ver = doc.current_media_version
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
        files=[],
    )


def _linked_details_for_doc(doc: Document, linked_raw: list) -> list[LinkedDocumentDetail]:
    return [LinkedDocumentDetail(**r) for r in linked_raw]


@router.post("/", response_model=APIResponse, status_code=201)
async def create_document(
    data: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload = DocumentSavePayload.model_validate_json(data)
    doc = await document_service.save_document(db, user, payload, files=files or None)
    await cache_delete(f"item:document:{doc.id}")
    linked_details = None
    if doc.linked_document_ids:
        raw = await document_service.get_linked_document_details(db, doc.linked_document_ids)
        linked_details = _linked_details_for_doc(doc, raw)
    return APIResponse(message="Document created", status_code=201, status="success", data=_to_out(doc, linked_details))


@router.put("/{document_id}", response_model=APIResponse)
async def update_document(
    document_id: int,
    data: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload = DocumentSavePayload.model_validate_json(data)
    doc = await document_service.save_document(db, user, payload, document_id=document_id, files=files or None)
    await cache_delete(f"item:document:{document_id}")
    if doc.id != document_id:
        await cache_delete(f"item:document:{doc.id}")
    linked_details = None
    if doc.linked_document_ids:
        raw = await document_service.get_linked_document_details(db, doc.linked_document_ids)
        linked_details = _linked_details_for_doc(doc, raw)
    return APIResponse(message="Document updated", status_code=200, status="success", data=_to_out(doc, linked_details))


@router.get("/", response_model=APIResponsePaginated)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: DocumentStatus | None = None,
    document_type: str | None = Query(None, description="Display label e.g. 'Policy'"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc_type_enum: DocumentType | None = None
    if document_type:
        doc_type_enum = LABEL_TO_DOCUMENT_TYPE.get((document_type or "").strip())
        if doc_type_enum is None:
            raise HTTPException(400, detail="Invalid document_type")
    docs, total = await document_service.list_documents(db, page, page_size, status, doc_type_enum)
    return APIResponsePaginated(
        message="Documents fetched",
        status_code=200,
        status="success",
        data=[_to_list_out(d) for d in docs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/hub", response_model=APIResponse)
async def document_hub(
    doc_types: list[str] | None = Query(None, description="Document type(s) — enum or label. Omit for all types."),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    applicability: str | None = Query(None, description="ALL | DIVISION | EMPLOYEE"),
    search: str | None = Query(None, description="Search name, summary, tags"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cache_key = f"doc_hub:{user.id}:{doc_types}:{page}:{page_size}:{applicability}:{search}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return APIResponse(
            message="Documents fetched",
            status_code=200,
            status="success",
            data=cached,
        )

    hub = await document_service.get_document_hub(
        db,
        user,
        doc_types=doc_types,
        page=page,
        page_size=page_size,
        applicability=applicability,
        search=search,
    )
    await cache_set(cache_key, hub.model_dump(), ttl=settings.ITEM_DETAIL_CACHE_TTL_SECONDS)
    return APIResponse(
        message="Documents fetched",
        status_code=200,
        status="success",
        data=hub,
    )


@router.get("/linked-options", response_model=APIResponse)
async def linked_options(
    document_type: str = Query(..., description="Display label e.g. 'Policy'"),
    exclude_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc_type_enum = LABEL_TO_DOCUMENT_TYPE.get((document_type or "").strip())
    if doc_type_enum is None:
        raise HTTPException(400, detail="Invalid document_type")
    options = await document_service.get_linked_options(db, doc_type_enum, exclude_id)
    data = [LinkedOptionOut(**o) for o in options]
    return APIResponse(message="Linked options fetched", status_code=200, status="success", data=data)


@router.get("/{document_id}", response_model=APIResponse)
async def get_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = await document_service.get_document_for_detail(db, document_id)
    linked_details: list[LinkedDocumentDetail] | None = None
    if doc.linked_document_ids:
        raw = await document_service.get_linked_document_details(db, doc.linked_document_ids)
        linked_details = [LinkedDocumentDetail(**r) for r in raw]
    return APIResponse(message="Document fetched", status_code=200, status="success", data=_to_out(doc, linked_details))


@router.post("/{document_id}/draft", response_model=APIResponse, status_code=201)
async def create_draft(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    draft = await document_service.create_draft_from_document(db, document_id, user.id)
    return APIResponse(message="Draft created", status_code=201, status="success", data=_to_out(draft))


@router.patch("/{document_id}/toggle-status", response_model=APIResponse)
async def toggle_status(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = await document_service.toggle_document_status(db, document_id, user)
    return APIResponse(message="Status updated", status_code=200, status="success", data=_to_out(doc))


@router.delete("/{document_id}", response_model=APIResponse)
async def deactivate_document(
    document_id: int,
    payload: DeactivatePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await document_service.deactivate_document(db, document_id, payload.deactivate_remarks, user.id)
    return APIResponse(message="Document deactivated", status_code=200, status="success", data=None)


# ── Revisions ────────────────────────────────────────────────────────────

@router.get("/{document_id}/revisions/", response_model=APIResponse)
async def list_revisions(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    revs = await document_service.list_revisions(db, document_id)
    data = [
        RevisionListItemOut(
            id=r.id,
            document_id=r.document_id,
            media_version=r.media_version,
            revision_number=r.revision_number,
            version_display=f"{r.media_version}.{r.revision_number}",
            created_at=r.created_at,
        )
        for r in revs
    ]
    return APIResponse(message="Revisions fetched", status_code=200, status="success", data=data)


@router.get("/{document_id}/revisions/{media_version}/{revision_number}", response_model=APIResponse)
async def get_revision(
    document_id: int,
    media_version: int,
    revision_number: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rev = await document_service.get_revision(db, document_id, media_version, revision_number)
    data = DocumentRevisionOut(
        id=rev.id,
        document_id=rev.document_id,
        media_version=rev.media_version,
        revision_number=rev.revision_number,
        version_display=f"{rev.media_version}.{rev.revision_number}",
        name=rev.name,
        document_type=document_type_to_label(rev.document_type.value),
        tags=rev.tags,
        summary=rev.summary,
        applicability_type=rev.applicability_type,
        applicability_refs=rev.applicability_refs,
        created_by=rev.created_by,
        created_by_name=rev.creator.full_name,
        created_at=rev.created_at,
    )
    return APIResponse(message="Revision fetched", status_code=200, status="success", data=data)
