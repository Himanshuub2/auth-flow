import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.events.event import Event, EventRevision
from app.models.events.event_media_item import EventMediaItem

logger = logging.getLogger(__name__)


async def list_revisions(db: AsyncSession, event_id: int):
    """
    List revisions for a given event.
    Only fetches id, event_id, media_version, revision_number, created_at
    to keep the query fast and the payload small.
    :param db: The database session
    :param event_id: The ID of the event
    :return: A list of revisions
    """
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

    media_result = await db.execute(
        select(EventMediaItem)
        .where(
            EventMediaItem.event_id == event_id,
            EventMediaItem.media_versions.contains([media_version]),
        )
        .order_by(EventMediaItem.sort_order)
    )
    media_items = list(media_result.scalars().all())
    return revision, media_items
