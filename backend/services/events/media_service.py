import logging
import uuid

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.events.event import Event, EventRevision
from models.events.event_media_item import EventMediaItem, FileType
from schemas.events.event import FileMetadataIn
from storage import get_storage

logger = logging.getLogger(__name__)


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


def _validate_file_size(file_type: FileType, size: int, filename: str) -> None:
    limit = settings.MAX_IMAGE_SIZE_BYTES if file_type == FileType.IMAGE else settings.MAX_VIDEO_SIZE_BYTES
    if size > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File '{filename}' exceeds the {limit // (1024*1024)}MB limit",
        )


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

    for file in files:
        filename = file.filename or "unknown"
        if filename not in thumbnail_filenames:
            continue
        try:
            content = await file.read()
            await file.seek(0)
            if not _is_thumbnail_extension(filename):
                logger.warning("Thumbnail file %s is not an image; skipping", filename)
                continue
            ext = filename.rsplit(".", 1)[-1].lower()
            dest_path = f"{event_id}/thumb_{uuid.uuid4().hex}.{ext}"
            await storage.save(file, dest_path)
            thumb_urls[filename] = storage.get_url(dest_path)
            logger.debug("Uploaded thumbnail %s for event %s", filename, event_id)
        except Exception as e:
            logger.exception("Failed to upload thumbnail %s: %s", filename, e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Thumbnail upload failed: {filename}",
            ) from e

    saved: list[EventMediaItem] = []
    for file in files:
        filename = file.filename or "unknown"
        if filename in thumbnail_filenames:
            continue

        file_type = _classify_file(filename)
        content = await file.read()
        file_size = len(content)
        await file.seek(0)
        _validate_file_size(file_type, file_size, filename)

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

        ext = filename.rsplit(".", 1)[-1].lower()
        dest_path = f"{event_id}/{uuid.uuid4().hex}.{ext}"
        await storage.save(file, dest_path)

        item = EventMediaItem(
            event_id=event_id,
            file_type=file_type,
            file_url=storage.get_url(dest_path),
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
