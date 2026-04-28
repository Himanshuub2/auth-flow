from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.events.event import Event, EventRevision
from models.events.event_media_item import EventMediaItem


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
