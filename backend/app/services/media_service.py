import logging
import uuid

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.event import Event
from app.models.event_media_item import EventMediaItem, FileType
from app.storage import get_storage

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


def _validate_file_size(file_type: FileType, size: int, filename: str) -> None:
    limit = settings.MAX_IMAGE_SIZE_BYTES if file_type == FileType.IMAGE else settings.MAX_VIDEO_SIZE_BYTES
    if size > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File '{filename}' exceeds the {limit // (1024*1024)}MB limit",
        )


async def upload_files(
    db: AsyncSession, event_id: int, files: list[UploadFile]
) -> list[EventMediaItem]:
    """Upload files. One row per unique filename per event."""
    storage = get_storage()
    saved: list[EventMediaItem] = []

    for file in files:
        filename = file.filename or "unknown"
        file_type = _classify_file(filename)

        content = await file.read()
        file_size = len(content)
        await file.seek(0)

        _validate_file_size(file_type, file_size, filename)

        existing = (await db.execute(
            select(EventMediaItem).where(
                EventMediaItem.event_id == event_id,
                EventMediaItem.original_filename == filename,
            ).limit(1)
        )).scalar_one_or_none()

        if existing:
            if 0 not in existing.media_versions:
                existing.media_versions = [*existing.media_versions, 0]
            saved.append(existing)
            continue

        ext = filename.rsplit(".", 1)[-1].lower()
        dest_path = f"{event_id}/{uuid.uuid4().hex}.{ext}"
        await storage.save(file, dest_path)

        item = EventMediaItem(
            event_id=event_id,
            media_versions=[0],
            file_type=file_type,
            file_url=storage.get_url(dest_path),
            sort_order=len(saved),
            file_size_bytes=file_size,
            original_filename=filename,
        )
        db.add(item)
        saved.append(item)

    await db.flush()
    logger.info("Uploaded %d files for event %s", len(saved), event_id)
    return saved


async def get_media_items(
    db: AsyncSession, event_id: int, version: int | None = None
) -> list[EventMediaItem]:
    if version is None:
        event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
        if not event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        version = event.current_media_version

    result = await db.execute(
        select(EventMediaItem)
        .where(
            EventMediaItem.event_id == event_id,
            EventMediaItem.media_versions.any(version),
        )
        .order_by(EventMediaItem.sort_order)
    )
    return list(result.scalars().all())
