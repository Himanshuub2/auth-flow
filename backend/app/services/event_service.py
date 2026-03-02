import logging

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.event import Event, EventRevision, EventStatus, ApplicabilityType
from app.models.event_media_item import EventMediaItem
from app.schemas.event import EventSavePayload
from app.services.media_service import upload_files

logger = logging.getLogger(__name__)


async def save_event(
    db: AsyncSession,
    user_id: int,
    payload: EventSavePayload,
    *,
    event_id: int | None = None,
    files: list[UploadFile] | None = None,
) -> Event:
    if event_id:
        event = await get_event(db, event_id)
    else:
        event = Event(created_by=user_id)
        db.add(event)
        await db.flush()

    # Saving a PUBLISHED event as DRAFT → create/reuse a linked draft instead
    if event.status == EventStatus.PUBLISHED and payload.status == EventStatus.DRAFT:
        event = await _get_or_create_draft(db, event, user_id)

    event.event_name = payload.event_name
    event.sub_event_name = payload.sub_event_name
    event.event_dates = payload.event_dates
    event.description = payload.description
    event.tags = payload.tags
    event.applicability_type = payload.applicability_type
    event.applicability_refs = payload.applicability_refs

    if files:
        await upload_files(db, event.id, files)

    if payload.status == EventStatus.PUBLISHED:
        if event.draft_parent_id is not None:
            return await _publish_draft(db, event)
        await _publish_event(db, event)
    else:
        event.status = EventStatus.DRAFT

    await db.flush()
    await db.refresh(event)
    return event


async def get_event(db: AsyncSession, event_id: int) -> Event:
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


async def list_events(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status_filter: EventStatus | None = None,
) -> tuple[list[Event], int]:
    query = select(Event)
    count_query = select(func.count()).select_from(Event)

    if status_filter:
        query = query.where(Event.status == status_filter)
        count_query = count_query.where(Event.status == status_filter)

    total = (await db.execute(count_query)).scalar() or 0
    query = (
        query.options(selectinload(Event.media_items), selectinload(Event.creator))
        .order_by(Event.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    events = list((await db.execute(query)).scalars().all())
    return events, total


async def delete_event(db: AsyncSession, event_id: int) -> None:
    event = await get_event(db, event_id)
    event.status = EventStatus.ARCHIVED
    await db.flush()


async def create_draft_from_event(db: AsyncSession, parent_event_id: int, user_id: int) -> Event:
    parent = await get_event(db, parent_event_id)
    if parent.status != EventStatus.PUBLISHED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Can only create drafts from published events")
    draft = await _get_or_create_draft(db, parent, user_id)
    await db.refresh(draft)
    return draft


async def _get_or_create_draft(db: AsyncSession, parent: Event, user_id: int) -> Event:
    """Return existing draft for this published event, or create a new one."""
    existing = (await db.execute(
        select(Event).where(
            Event.draft_parent_id == parent.id,
            Event.status == EventStatus.DRAFT,
        )
    )).scalar_one_or_none()
    if existing:
        return existing

    draft = Event(
        event_name=parent.event_name,
        sub_event_name=parent.sub_event_name,
        event_dates=parent.event_dates,
        description=parent.description,
        tags=parent.tags,
        current_media_version=parent.current_media_version,
        current_revision_number=parent.current_revision_number,
        status=EventStatus.DRAFT,
        applicability_type=parent.applicability_type,
        applicability_refs=parent.applicability_refs,
        draft_parent_id=parent.id,
        created_by=user_id,
    )
    db.add(draft)
    await db.flush()
    await _copy_media(db, parent.id, parent.current_media_version, 0, target_event_id=draft.id)
    await db.flush()
    return draft


# ── publish ──────────────────────────────────────────────────────────────

async def _publish_event(db: AsyncSession, event: Event) -> None:
    """First publish or re-publish of a standalone event."""
    if event.current_media_version == 0:
        event.current_media_version = 1
        event.current_revision_number = 0
        # Move staging files (version 0) to version 1
        await db.execute(
            sa_update(EventMediaItem)
            .where(EventMediaItem.event_id == event.id, EventMediaItem.media_version == 0)
            .values(media_version=1)
        )
    else:
        if await _version_should_bump(db, event):
            event.current_media_version += 1
            event.current_revision_number = 0
            await _copy_media(db, event.id, 0, event.current_media_version)
        else:
            event.current_revision_number += 1

    db.add(EventRevision(
        event_id=event.id,
        media_version=event.current_media_version,
        revision_number=event.current_revision_number,
        event_name=event.event_name,
        sub_event_name=event.sub_event_name,
        event_dates=event.event_dates,
        description=event.description,
        tags=event.tags,
        created_by=event.created_by,
    ))
    event.status = EventStatus.PUBLISHED


async def _publish_draft(db: AsyncSession, draft: Event) -> Event:
    """Publish a draft: archive the parent, promote the draft with full history."""
    parent = await get_event(db, draft.draft_parent_id)

    last_rev = _find_latest_revision(parent)
    name_changed = (
        draft.event_name != last_rev.event_name
        or draft.sub_event_name != last_rev.sub_event_name
    ) if last_rev else True
    files_changed = await _files_differ(db, draft.id, 0, parent.current_media_version, parent.id)

    if name_changed or files_changed:
        draft.current_media_version = parent.current_media_version + 1
        draft.current_revision_number = 0
        await _copy_media(db, draft.id, 0, draft.current_media_version)
    else:
        draft.current_media_version = parent.current_media_version
        draft.current_revision_number = parent.current_revision_number + 1

    # Move parent's revisions and media to draft so it has full history
    for rev in parent.revisions:
        rev.event_id = draft.id
    await db.execute(
        sa_update(EventMediaItem)
        .where(EventMediaItem.event_id == parent.id)
        .values(event_id=draft.id)
    )

    db.add(EventRevision(
        event_id=draft.id,
        media_version=draft.current_media_version,
        revision_number=draft.current_revision_number,
        event_name=draft.event_name,
        sub_event_name=draft.sub_event_name,
        event_dates=draft.event_dates,
        description=draft.description,
        tags=draft.tags,
        created_by=draft.created_by,
    ))

    parent.status = EventStatus.ARCHIVED
    draft.status = EventStatus.PUBLISHED
    draft.draft_parent_id = None

    await db.flush()
    await db.refresh(draft)
    return draft


# ── helpers ──────────────────────────────────────────────────────────────

def _find_latest_revision(event: Event) -> EventRevision | None:
    if not event.revisions:
        return None
    return max(event.revisions, key=lambda r: (r.media_version, r.revision_number))


async def _version_should_bump(db: AsyncSession, event: Event) -> bool:
    last_rev = _find_latest_revision(event)
    if not last_rev:
        return True
    name_changed = (
        event.event_name != last_rev.event_name
        or event.sub_event_name != last_rev.sub_event_name
    )
    if name_changed:
        return True
    return await _files_differ(db, event.id, 0, event.current_media_version)


async def _get_hashes(db: AsyncSession, event_id: int, media_version: int) -> set[str]:
    result = await db.execute(
        select(EventMediaItem.file_hash).where(
            EventMediaItem.event_id == event_id,
            EventMediaItem.media_version == media_version,
        )
    )
    return set(result.scalars().all())


async def _files_differ(
    db: AsyncSession, event_id_a: int, version_a: int, version_b: int,
    event_id_b: int | None = None,
) -> bool:
    hashes_a = await _get_hashes(db, event_id_a, version_a)
    hashes_b = await _get_hashes(db, event_id_b or event_id_a, version_b)
    return hashes_a != hashes_b


async def _copy_media(
    db: AsyncSession, source_event_id: int, source_version: int,
    target_version: int, target_event_id: int | None = None,
) -> None:
    target_eid = target_event_id or source_event_id
    result = await db.execute(
        select(EventMediaItem).where(
            EventMediaItem.event_id == source_event_id,
            EventMediaItem.media_version == source_version,
        ).order_by(EventMediaItem.sort_order)
    )
    for item in result.scalars().all():
        db.add(EventMediaItem(
            event_id=target_eid,
            media_version=target_version,
            file_type=item.file_type,
            file_url=item.file_url,
            file_hash=item.file_hash,
            thumbnail_url=item.thumbnail_url,
            caption=item.caption,
            description=item.description,
            sort_order=item.sort_order,
            file_size_bytes=item.file_size_bytes,
            original_filename=item.original_filename,
        ))
