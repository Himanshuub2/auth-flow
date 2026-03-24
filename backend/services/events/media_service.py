import logging
import uuid

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.events.event import Event, EventRevision
from models.events.event_media_item import EventMediaItem, FileType
from schemas.events.event import FileMetadataIn
from services.documents.document_file_service import (
    ALLOWED_IMAGE_MIME_TYPES,
    EXTENSION_TO_MIME_TYPES,
)
from storage import get_storage
from utils.magic_bytes import (
    normalize_content_type,
    read_prefix_and_rewind,
    validate_magic_prefix,
)

logger = logging.getLogger(__name__)

ALLOWED_VIDEO_MIME_TYPES = frozenset({"video/mp4", "application/mp4"})
VIDEO_EXTENSION_TO_MIME_TYPES: dict[str, set[str]] = {"mp4": set(ALLOWED_VIDEO_MIME_TYPES)}


def _classify_file(filename: str) -> FileType:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in settings.ALLOWED_IMAGE_EXTENSIONS:
        return FileType.IMAGE
    if ext in settings.ALLOWED_VIDEO_EXTENSIONS:
        return FileType.VIDEO
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported file extension: .{ext}",
    )


def _is_thumbnail_extension(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in settings.ALLOWED_IMAGE_EXTENSIONS


def _validate_event_mime_type(filename: str, content_type: str | None, file_type: FileType) -> None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if not ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File '{filename}' does not have a valid extension",
        )

    if file_type == FileType.IMAGE:
        mime_map = EXTENSION_TO_MIME_TYPES
        category_allowed = ALLOWED_IMAGE_MIME_TYPES
    else:
        mime_map = VIDEO_EXTENSION_TO_MIME_TYPES
        category_allowed = ALLOWED_VIDEO_MIME_TYPES

    normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if not normalized_content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing mime type for file '{filename}'",
        )

    allowed_for_extension = mime_map.get(ext)
    if not allowed_for_extension:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported extension '.{ext}' for file '{filename}'",
        )

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


def _validate_event_upload_size(file: UploadFile, filename: str, file_type: FileType) -> None:
    """Enforce max size when UploadFile.size is set (multipart Content-Length)."""
    limit = settings.MAX_IMAGE_SIZE_BYTES if file_type == FileType.IMAGE else settings.MAX_VIDEO_SIZE_BYTES
    sz = getattr(file, "size", None)
    if sz is None or not isinstance(sz, int) or sz < 0:
        return
    if sz > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File '{filename}' exceeds the {limit // (1024 * 1024)}MB limit",
        )


def _event_magic_mimes_for_extension(ext: str, file_type: FileType) -> frozenset[str]:
    if file_type == FileType.IMAGE:
        allowed = EXTENSION_TO_MIME_TYPES.get(ext)
        return frozenset(allowed) if allowed else frozenset()
    return frozenset({"video/mp4", "application/mp4"})


async def upload_files(
    db: AsyncSession,
    event_id: int,
    files: list[UploadFile],
    file_metadata: list[FileMetadataIn] | None = None,
) -> list[EventMediaItem]:
    """Upload files; apply caption, description, thumbnail from file_metadata."""
    if not files:
        return []

    meta_by_name = {m.original_filename: m for m in (file_metadata or [])}
    thumbnail_filenames = {
        m.thumbnail_original_filename
        for m in (file_metadata or [])
        if m.thumbnail_original_filename
    }

    storage = get_storage()
    thumb_urls: dict[str, str] = {}
    uploaded_paths: list[str] = []

    # Per file: extension/type → size → MIME → magic prefix (no upload until all pass).
    for file in files:
        filename = file.filename or "unknown"
        if filename in thumbnail_filenames:
            if not _is_thumbnail_extension(filename):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Thumbnail file '{filename}' must be an image",
                )
            file_type = FileType.IMAGE
        else:
            file_type = _classify_file(filename)

        ext = filename.rsplit(".", 1)[-1].lower()
        _validate_event_upload_size(file, filename, file_type)
        _validate_event_mime_type(filename, file.content_type, file_type)
        prefix = await read_prefix_and_rewind(file)
        validate_magic_prefix(filename, prefix, _event_magic_mimes_for_extension(ext, file_type))

    # Thumbnails first so thumb_urls is filled before main items that reference them.
    thumb_files = [f for f in files if (f.filename or "unknown") in thumbnail_filenames]
    main_files = [f for f in files if (f.filename or "unknown") not in thumbnail_filenames]
    upload_order = thumb_files + main_files

    saved: list[EventMediaItem] = []
    try:
        for file in upload_order:
            filename = file.filename or "unknown"
            ext = filename.rsplit(".", 1)[-1].lower()
            dest_path = f"{event_id}/{uuid.uuid4().hex}.{ext}"
            await file.seek(0)
            ct = normalize_content_type(file.content_type)
            await storage.save(
                file,
                dest_path,
                content_type=ct or None,
            )
            uploaded_paths.append(dest_path)
            public_url = storage.get_url(dest_path)

            if filename in thumbnail_filenames:
                thumb_urls[filename] = public_url
                logger.debug("Uploaded thumbnail %s for event %s", filename, event_id)
                continue

            file_type = _classify_file(filename)
            raw_size = getattr(file, "size", 0)
            file_size = raw_size if isinstance(raw_size, int) and raw_size >= 0 else 0

            meta = meta_by_name.get(filename)
            thumbnail_url = None
            if meta and meta.thumbnail_original_filename:
                thumbnail_url = thumb_urls.get(meta.thumbnail_original_filename)

            existing = (await db.execute(
                select(EventMediaItem).where(
                    EventMediaItem.event_id == event_id,
                    EventMediaItem.original_filename == filename,
                ).limit(1)
            )).scalar_one_or_none()

            if existing:
                if meta:
                    existing.caption = meta.caption
                    existing.description = meta.description
                    if thumbnail_url is not None:
                        existing.thumbnail_url = thumbnail_url
                saved.append(existing)
                continue

            item = EventMediaItem(
                event_id=event_id,
                file_type=file_type,
                file_url=public_url,
                thumbnail_url=thumbnail_url,
                caption=meta.caption if meta else None,
                description=meta.description if meta else None,
                sort_order=len(saved),
                file_size_bytes=file_size,
                original_filename=filename,
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
        logger.exception("Failed to upload event files for event %s", event_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upload failed; no files were saved",
        ) from exc
    logger.info("Uploaded %d files for event %s (with metadata)", len(saved), event_id)
    return saved


async def get_media_items(
    db: AsyncSession, event_id: int, version: int | None = None
) -> list[EventMediaItem]:
    if version is None:
        event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
        if not event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        version = event.current_media_version

    file_ids = await _get_file_ids_for_version(db, event_id, version)
    if not file_ids:
        return []

    result = await db.execute(
        select(EventMediaItem)
        .where(EventMediaItem.event_id == event_id)
        .order_by(EventMediaItem.sort_order)
    )
    all_files = list(result.scalars().all())
    id_set = set(file_ids)
    return [f for f in all_files if f.id in id_set]


async def _get_file_ids_for_version(db: AsyncSession, event_id: int, version: int) -> list[int]:
    """Get file IDs for a version from the event's staging or revision."""
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event:
        return []
    if version == 0:
        return list(event.staging_file_ids or [])
    result = await db.execute(
        select(EventRevision.file_ids)
        .where(
            EventRevision.event_id == event_id,
            EventRevision.media_version == version,
        )
        .order_by(EventRevision.revision_number.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return list(row)
    return list(event.staging_file_ids or [])
