import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.events.event import Event, EventRevision
from models.events.event_media_item import EventMediaItem

logger = logging.getLogger(__name__)


async def list_revisions(db: AsyncSession, event_id: int):
    result = await db.execute(
        select(
            EventRevision.id,
            EventRevision.event_id,
            EventRevision.media_version,
            EventRevision.revision_number,
            EventRevision.change_remarks,
            EventRevision.created_at,
        )
        .where(EventRevision.event_id == event_id)
        .order_by(
            EventRevision.media_version.desc(),
            EventRevision.revision_number.desc(),
        )
    )
    rows = result.all()
    if not rows:
        event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
        if not event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return rows


async def get_revision_snapshot(
    db: AsyncSession, event_id: int, media_version: int, revision_number: int
) -> tuple[EventRevision, list[EventMediaItem]]:
    result = await db.execute(
        select(EventRevision)
        .where(
            EventRevision.event_id == event_id,
            EventRevision.media_version == media_version,
            EventRevision.revision_number == revision_number,
        )
        .options(selectinload(EventRevision.creator))
    )
    revision = result.scalar_one_or_none()
    if not revision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Revision {media_version}.{revision_number} not found",
        )

    file_ids = revision.file_ids or []
    if not file_ids:
        return revision, []

    media_result = await db.execute(
        select(EventMediaItem)
        .where(EventMediaItem.event_id == event_id)
        .order_by(EventMediaItem.sort_order)
    )
    all_items = list(media_result.scalars().all())
    id_set = set(file_ids)
    media_items = [f for f in all_items if f.id in id_set]
    return revision, media_items
