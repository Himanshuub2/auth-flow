from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.events.event import Event, EventStatus
from models.events.event_like import EventLike


async def event_ids_liked_by_user(
    db: AsyncSession, staff_id: str, event_ids: list[int]
) -> set[int]:
    if not event_ids:
        return set()
    result = await db.execute(
        select(EventLike.event_id).where(
            EventLike.staff_id == staff_id,
            EventLike.event_id.in_(event_ids),
        )
    )
    return {row[0] for row in result.all()}


async def is_liked(db: AsyncSession, staff_id: str, event_id: int) -> bool:
    result = await db.execute(
        select(EventLike.id).where(
            EventLike.event_id == event_id,
            EventLike.staff_id == staff_id,
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def like_event(db: AsyncSession, event_id: int, staff_id: str) -> tuple[int, bool]:
    event = await _get_event_for_like(db, event_id)
    existing = await db.execute(
        select(EventLike).where(
            EventLike.event_id == event_id,
            EventLike.staff_id == staff_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return event.like_count, True

    db.add(EventLike(event_id=event_id, staff_id=staff_id))
    event.like_count += 1
    await db.flush()
    await db.refresh(event)
    return event.like_count, True


async def unlike_event(db: AsyncSession, event_id: int, staff_id: str) -> tuple[int, bool]:
    event = await _get_event_for_like(db, event_id)
    result = await db.execute(
        delete(EventLike).where(
            EventLike.event_id == event_id,
            EventLike.staff_id == staff_id,
        )
    )
    if result.rowcount == 0:
        return event.like_count, False

    event.like_count = max(0, event.like_count - 1)
    await db.flush()
    await db.refresh(event)
    return event.like_count, False


async def _get_event_for_like(db: AsyncSession, event_id: int) -> Event:
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if event.status != EventStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only active events can be liked",
        )
    return event
