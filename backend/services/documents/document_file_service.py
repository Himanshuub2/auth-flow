import logging
import uuid

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.documents.document import DOCUMENT_TYPE_ALLOWED_EXTENSIONS, DocumentType
from models.documents.document_file import DocumentFile, DocumentFileType
from storage import get_storage
from utils.magic_bytes import (
    normalize_content_type,
    read_prefix_and_rewind,
    validate_magic_prefix,
)

logger = logging.getLogger(__name__)

MIN_FILES = 1
MAX_FILES = 6
ALLOWED_IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/bmp",
    "image/tiff",
}
ALLOWED_DOCUMENT_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
EXTENSION_TO_MIME_TYPES: dict[str, set[str]] = {
    "png": {"image/png"},
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
    "gif": {"image/gif"},
    "bmp": {"image/bmp"},
    "tiff": {"image/tiff"},
    "pdf": {"application/pdf"},
    "doc": {"application/msword"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    "xls": {"application/vnd.ms-excel"},
    "xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    "ppt": {"application/vnd.ms-powerpoint"},
    "pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
}

# Extra types `filetype` may return for the first bytes (OLE / ZIP containers).
EXTENSION_MAGIC_EXTRAS: dict[str, set[str]] = {
    "doc": {"application/x-cfb", "application/msword"},
    "xls": {"application/x-cfb", "application/vnd.ms-excel"},
    "ppt": {"application/x-cfb", "application/vnd.ms-powerpoint"},
    "docx": {
        "application/zip",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
    "xlsx": {
        "application/zip",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    },
    "pptx": {
        "application/zip",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    },
}


def _extension_magic_mimes(ext: str) -> frozenset[str]:
    base = EXTENSION_TO_MIME_TYPES.get(ext)
    if not base:
        return frozenset()
    return frozenset(base | EXTENSION_MAGIC_EXTRAS.get(ext, set()))


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


def _validate_mime_type_for_extension(filename: str, content_type: str | None) -> None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if not ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File '{filename}' does not have a valid extension",
        )

    normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if not normalized_content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing mime type for file '{filename}'",
        )

    allowed_for_extension = EXTENSION_TO_MIME_TYPES.get(ext)
    if not allowed_for_extension:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported extension '.{ext}' for file '{filename}'",
        )

    category_allowed = ALLOWED_IMAGE_MIME_TYPES | ALLOWED_DOCUMENT_MIME_TYPES
    if normalized_content_type not in category_allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported mime type '{normalized_content_type}' for file '{filename}'",
        )

    if normalized_content_type not in allowed_for_extension:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Mime type '{normalized_content_type}' does not match "
                f"extension '.{ext}' for file '{filename}'"
            ),
        )


def _validate_document_upload_size(file: UploadFile, filename: str) -> None:
    """Enforce max size when the multipart part exposes Content-Length (UploadFile.size)."""
    limit = settings.MAX_DOCUMENT_FILE_SIZE_BYTES
    sz = getattr(file, "size", None)
    if sz is None or not isinstance(sz, int) or sz < 0:
        return
    if sz > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File '{filename}' exceeds the {limit // (1024 * 1024)}MB limit",
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
    uploaded_paths: list[str] = []

    # Enforce max file counts before uploading or saving anything
    existing_count = (await db.execute(
        select(func.count())
        .select_from(DocumentFile)
        .where(DocumentFile.document_id == document_id)
    )).scalar_one() or 0

    if document_type == DocumentType.FAQ:
        # FAQs are limited to a single file total
        if existing_count + len(files) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="FAQ documents can only have 1 file",
            )
    else:
        if existing_count + len(files) > MAX_FILES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum {MAX_FILES} files allowed",
            )

    # Validate all files in order before any upload: type → size → MIME → magic prefix.
    for file in files:
        filename = file.filename or "unknown"
        _validate_extension_for_type(filename, document_type)

    for file in files:
        filename = file.filename or "unknown"
        _validate_document_upload_size(file, filename)

    for file in files:
        filename = file.filename or "unknown"
        _validate_mime_type_for_extension(filename, file.content_type)

    for file in files:
        filename = file.filename or "unknown"
        ext = filename.rsplit(".", 1)[-1].lower()
        prefix = await read_prefix_and_rewind(file)
        validate_magic_prefix(filename, prefix, _extension_magic_mimes(ext))

    try:
        for file in files:
            filename = file.filename or "unknown"
            raw_size = getattr(file, "size", 0)
            file_size = raw_size if isinstance(raw_size, int) and raw_size >= 0 else 0
            await file.seek(0)

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
            if document_type == DocumentType.FAQ:
                dest_path = f"documents/faqs/{uuid.uuid4().hex}.{ext}"
            else:
                dest_path = f"documents/{uuid.uuid4().hex}.{ext}"
            ct = normalize_content_type(file.content_type)
            await storage.save(
                file,
                dest_path,
                content_type=ct or None,
                content_disposition="attachment",
            )
            uploaded_paths.append(dest_path)

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
    except Exception as exc:
        for path in reversed(uploaded_paths):
            try:
                await storage.delete(path)
            except Exception:
                logger.warning("Failed to rollback uploaded file: %s", path, exc_info=True)

        if isinstance(exc, HTTPException):
            raise
        logger.exception("Failed to upload document files for document %s", document_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upload failed; no files were saved",
        ) from exc

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
