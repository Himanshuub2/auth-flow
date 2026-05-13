import asyncio
import json
import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session_factory, get_db
from models.documents.document import DocumentType
from schemas.documents.bulk_applicability import (
    BulkApplicabilityHistoryItem,
    DownloadTemplateRequest,
)
from schemas.events.comman import APIResponse, APIResponsePaginated
from services.documents import bulk_applicability_service as svc
from storage import get_storage
from utils.security import CurrentUser, is_active_master_or_policy_or_kh_admin

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSIONS = frozenset({"xlsx", "csv", "xls"})
BLOB_PREFIX = "bulk-applicability"
SSE_HEARTBEAT_SEC = 20.0


def _sse_chunk(event: dict) -> bytes:
    return f"data: {json.dumps(event)}\n\n".encode("utf-8")

_CONTENT_TYPE_BY_EXT = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv; charset=utf-8",
}


def _get_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


@router.post("/download-template")
async def download_template(
    body: DownloadTemplateRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(is_active_master_or_policy_or_kh_admin),
):
    buf, filename = await svc.generate_template(
        db,
        mode=body.mode.value,
        selected_types=body.selected_types,
        document_ids=body.document_ids,
        event_ids=body.event_ids,
    )
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/upload")
async def upload_bulk_file(
    file: UploadFile = File(...),
    selected_types: str | None = Form(
        None,
        description="Optional comma-separated types, e.g. POLICY,EWS,EVENTS. If omitted, all types are processed.",
    ),
    change_remarks: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(is_active_master_or_policy_or_kh_admin),
):
    if not file.filename:
        raise HTTPException(400, detail="File name is required")

    ext = _get_extension(file.filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            detail=f"Invalid file extension '.{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    if selected_types:
        types_list = [t.strip().upper() for t in selected_types.split(",") if t.strip()]
    else:
        types_list = [t.value for t in DocumentType] + ["EVENTS"]

    slug = uuid.uuid4().hex[:12]
    safe_name = os.path.basename(file.filename)
    blob_path = f"{BLOB_PREFIX}/{slug}/{safe_name}"
    storage = get_storage()
    content_type = file.content_type or _CONTENT_TYPE_BY_EXT.get(ext)
    try:
        await storage.save(file, blob_path, content_type=content_type)
    except Exception:
        logger.exception("Azure upload failed for bulk applicability")
        raise HTTPException(502, detail="Failed to upload file to blob storage.")

    req = await svc.create_upload_request(
        db,
        file_name=file.filename,
        blob_path=blob_path,
        selected_types=types_list,
        change_remarks=change_remarks,
        user_id=user.id,
    )
    # Persist the PENDING row before streaming processing so rollback in the worker
    # session cannot undo this insert.
    await db.commit()

    request_id = req.id
    actor_id = user.id

    async def event_stream():
        yield _sse_chunk({"type": "started", "request_id": request_id})

        async def process_one():
            async with async_session_factory() as session:
                try:
                    return await svc.process_request_by_id(session, request_id, user_id=actor_id)
                except Exception as exc:
                    logger.exception("Bulk applicability stream processing failed for request %s", request_id)
                    return {"request_id": request_id, "status": "error", "error_message": str(exc)}

        task = asyncio.create_task(process_one())
        try:
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=SSE_HEARTBEAT_SEC)
                if task in done:
                    break
                yield _sse_chunk({"type": "keepalive"})
            result = await task
        except asyncio.CancelledError:
            task.cancel()
            raise
        yield _sse_chunk({"type": "complete", **result})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history", response_model=APIResponsePaginated)
async def get_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    request_id: int | None = Query(
        None,
        description="return only this request with a fresh file_sas_url.",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(is_active_master_or_policy_or_kh_admin),
):
    storage = get_storage()

    if request_id is not None:
        item = await svc.get_history_by_id(db, request_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Bulk applicability request not found")
        file_sas_url = storage.get_read_url(item.uploaded_file_url)
        data = [
            BulkApplicabilityHistoryItem(
                id=item.id,
                updated_by=f"{item.creator.username} ({item.created_by})" if item.creator else item.created_by,
                updated_on=item.updated_at,
                status=item.status,
                file_name=item.file_name,
                file_sas_url=file_sas_url,
                error=item.error_message,
                change_remarks=item.change_remarks,
            ).model_dump()
        ]
        return APIResponse(
            message="History fetched",
            status_code=200,
            status="success",
            data=data[0],
        )

    items, total = await svc.list_history(db, page, page_size)

    data = []
    for item in items:
        data.append(
            BulkApplicabilityHistoryItem(
                id=item.id,
                updated_by=f"{item.creator.username} ({item.created_by})" if item.creator else item.created_by,
                updated_on=item.updated_at,
                status=item.status,
                file_name=item.file_name,
                file_sas_url=None,
                error=item.error_message,
                change_remarks=item.change_remarks,
            ).model_dump()
        )

    return APIResponsePaginated(
        message="History fetched",
        status_code=200,
        status="success",
        data=data,
        total=total,
        page=page,
        page_size=page_size,
    )
