import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.documents.document import DocumentType
from schemas.documents.bulk_applicability import (
    BulkApplicabilityHistoryItem,
    BulkApplicabilityUploadOut,
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
    buf, filename = await svc.generate_template(db, body.selected_types)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/upload", response_model=APIResponse, status_code=202)
async def upload_bulk_file(
    file: UploadFile = File(...),
    selected_types: str | None = Form(
        None,
        description="Optional comma-separated types, e.g. POLICY,EWS,EVENTS. If omitted, all types are processed.",
    ),
    change_remarks: str | None = Form(None),
    force_start: bool = Form(False, description="If true, process immediately instead of queuing for cron"),
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
    # Persist the PENDING row before processing so a processing rollback cannot
    # remove this insert when force_start runs in the same request.
    await db.commit()

    if force_start:
        try:
            await svc.process_pending_requests(db, user_id=user.id)
        except Exception:
            logger.exception("Force-start processing failed for request %s", req.id)

    return APIResponse(
        message="File uploaded successfully. Processing queued."
        if not force_start
        else "File uploaded and processing started.",
        status_code=202,
        status="success",
        data=BulkApplicabilityUploadOut(
            request_id=req.id,
            message="Processing queued" if not force_start else "Processing started",
        ).model_dump(),
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
                updated_by=item.creator.username if item.creator else item.created_by,
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
                updated_by=item.creator.username if item.creator else item.created_by,
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


@router.post("/process-pending", response_model=APIResponse)
async def process_pending(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(is_active_master_or_policy_or_kh_admin),
):
    """
    Internal endpoint for cron / Azure Function to trigger processing.
    Can also be called manually by admins.
    """
    summary = await svc.process_pending_requests(db, user_id=user.id)
    return APIResponse(
        message="Processing complete",
        status_code=200,
        status="success",
        data=summary,
    )
