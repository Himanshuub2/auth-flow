import logging
import uuid

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.documents.document import DOCUMENT_TYPE_ALLOWED_EXTENSIONS, DocumentType
from app.models.documents.document_file import DocumentFile, DocumentFileType
from app.storage import get_storage

logger = logging.getLogger(__name__)

MIN_FILES = 1
MAX_FILES = 6


def _classify_doc_file(filename: str) -> DocumentFileType:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in settings.ALLOWED_IMAGE_EXTENSIONS:
        return DocumentFileType.IMAGE
    return DocumentFileType.DOCUMENT


def _validate_extension_for_type(filename: str, document_type: DocumentType) -> None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    allowed = DOCUMENT_TYPE_ALLOWED_EXTENSIONS.get(document_type, settings.ALLOWED_DOCUMENT_EXTENSIONS)
    if ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File '{filename}' with extension '.{ext}' is not allowed for document type {document_type.value}",
        )


def _validate_file_size(size: int, filename: str) -> None:
    if size > settings.MAX_DOCUMENT_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File '{filename}' exceeds the {settings.MAX_DOCUMENT_FILE_SIZE_BYTES // (1024*1024)}MB limit",
        )


def validate_file_count(count: int) -> None:
    if count < MIN_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"At least {MIN_FILES} file is required",
        )
    if count > MAX_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_FILES} files allowed",
        )


async def upload_document_files(
    db: AsyncSession,
    document_id: int,
    document_type: DocumentType,
    files: list[UploadFile],
) -> list[DocumentFile]:
    if not files:
        return []

    storage = get_storage()
    saved: list[DocumentFile] = []

    for file in files:
        filename = file.filename or "unknown"
        _validate_extension_for_type(filename, document_type)

        content = await file.read()
        file_size = len(content)
        await file.seek(0)
        _validate_file_size(file_size, filename)

        file_type = _classify_doc_file(filename)

        existing = (await db.execute(
            select(DocumentFile).where(
                DocumentFile.document_id == document_id,
                DocumentFile.original_filename == filename,
            ).limit(1)
        )).scalar_one_or_none()

        if existing:
            saved.append(existing)
            continue

        ext = filename.rsplit(".", 1)[-1].lower()
        dest_path = f"documents/{document_id}/{uuid.uuid4().hex}.{ext}"
        await storage.save(file, dest_path)

        item = DocumentFile(
            document_id=document_id,
            file_type=file_type,
            file_url=storage.get_url(dest_path),
            original_filename=filename,
            file_size_bytes=file_size,
            sort_order=len(saved),
        )
        db.add(item)
        saved.append(item)

    await db.flush()
    logger.info("Uploaded %d files for document %s", len(saved), document_id)
    return saved


async def get_document_files(
    db: AsyncSession, document_id: int, file_ids: list[int] | None = None,
) -> list[DocumentFile]:
    result = await db.execute(
        select(DocumentFile)
        .where(DocumentFile.document_id == document_id)
        .order_by(DocumentFile.sort_order)
    )
    all_files = list(result.scalars().all())
    if file_ids is not None:
        id_set = set(file_ids)
        return [f for f in all_files if f.id in id_set]
    return all_files
