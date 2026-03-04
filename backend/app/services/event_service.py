import logging

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.event import Event, EventRevision, EventStatus
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

    if event.status == EventStatus.PUBLISHED and payload.status == EventStatus.DRAFT:
        event = await _get_or_create_draft(db, event, user_id)

    event.event_name = payload.event_name
    event.sub_event_name = payload.sub_event_name
    event.event_dates = payload.event_dates
    event.description = payload.description
    event.tags = payload.tags
    event.applicability_type = payload.applicability_type
    event.applicability_refs = payload.applicability_refs

    uploaded_names: list[str] = []
    if files:
        uploaded = await upload_files(db, event.id, files)
        uploaded_names = [f.original_filename for f in uploaded]

    if payload.selected_filenames is not None:
        all_names = list(dict.fromkeys([*payload.selected_filenames, *uploaded_names]))
        await _sync_staging(db, event, all_names)

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
    event.status = EventStatus.INACTIVE
    await db.flush()


async def toggle_event_status(db: AsyncSession, event_id: int) -> Event:
    event = await get_event(db, event_id)
    if event.status == EventStatus.ACTIVE:
        event.status = EventStatus.INACTIVE
    elif event.status == EventStatus.INACTIVE:
        event.status = EventStatus.ACTIVE
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only ACTIVE/INACTIVE events can be toggled",
        )
    await db.flush()
    await db.refresh(event)
    return event


async def create_draft_from_event(db: AsyncSession, parent_event_id: int, user_id: int) -> Event:
    parent = await get_event(db, parent_event_id)
    if parent.status != EventStatus.PUBLISHED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Can only create drafts from published events")
    draft = await _get_or_create_draft(db, parent, user_id)
    await db.refresh(draft)
    return draft


async def _get_or_create_draft(db: AsyncSession, parent: Event, user_id: int) -> Event:
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

    parent_files = await _get_files_for_version(db, parent.id, parent.current_media_version)
    for f in parent_files:
        db.add(EventMediaItem(
            event_id=draft.id,
            media_versions=[0],
            file_type=f.file_type,
            file_url=f.file_url,
            thumbnail_url=f.thumbnail_url,
            caption=f.caption,
            description=f.description,
            sort_order=f.sort_order,
            file_size_bytes=f.file_size_bytes,
            original_filename=f.original_filename,
        ))
    await db.flush()
    return draft


# -- publish ---------------------------------------------------------------

async def _publish_event(db: AsyncSession, event: Event) -> None:
    if event.current_media_version == 0:
        event.current_media_version = 1
        event.current_revision_number = 0
        new_ver = 1
    else:
        if await _version_should_bump(db, event):
            event.current_media_version += 1
            event.current_revision_number = 0
        else:
            event.current_revision_number += 1
        new_ver = event.current_media_version

    staging = await _get_files_for_version(db, event.id, 0)
    for f in staging:
        clean = [v for v in f.media_versions if v != 0]
        if new_ver not in clean:
            clean.append(new_ver)
        f.media_versions = clean

    all_files = (await db.execute(
        select(EventMediaItem).where(EventMediaItem.event_id == event.id)
    )).scalars().all()
    staging_ids = {f.id for f in staging}
    for f in all_files:
        if f.id not in staging_ids and 0 in f.media_versions:
            f.media_versions = [v for v in f.media_versions if v != 0]

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
    parent = await get_event(db, draft.draft_parent_id)

    last_rev = _find_latest_revision(parent)
    name_changed = (
        draft.event_name != last_rev.event_name
        or draft.sub_event_name != last_rev.sub_event_name
    ) if last_rev else True
    files_changed = await _files_differ_between(db, draft.id, 0, parent.id, parent.current_media_version)

    if name_changed or files_changed:
        draft.current_media_version = parent.current_media_version + 1
        draft.current_revision_number = 0
    else:
        draft.current_media_version = parent.current_media_version
        draft.current_revision_number = parent.current_revision_number + 1

    new_ver = draft.current_media_version

    staging = await _get_files_for_version(db, draft.id, 0)
    for f in staging:
        clean = [v for v in f.media_versions if v != 0]
        if new_ver not in clean:
            clean.append(new_ver)
        f.media_versions = clean

    for rev in parent.revisions:
        rev.event_id = draft.id

    parent_files = (await db.execute(
        select(EventMediaItem).where(EventMediaItem.event_id == parent.id)
    )).scalars().all()
    for f in parent_files:
        f.event_id = draft.id

    db.add(EventRevision(
        event_id=draft.id,
        media_version=new_ver,
        revision_number=draft.current_revision_number,
        event_name=draft.event_name,
        sub_event_name=draft.sub_event_name,
        event_dates=draft.event_dates,
        description=draft.description,
        tags=draft.tags,
        created_by=draft.created_by,
    ))

    parent.status = EventStatus.INACTIVE
    draft.status = EventStatus.PUBLISHED
    draft.draft_parent_id = None

    await db.flush()
    await db.refresh(draft)
    return draft


# -- helpers ---------------------------------------------------------------

def _find_latest_revision(event: Event) -> EventRevision | None:
    if not event.revisions:
        return None
    return max(event.revisions, key=lambda r: (r.media_version, r.revision_number))


async def _version_should_bump(db: AsyncSession, event: Event) -> bool:
    last_rev = _find_latest_revision(event)
    if not last_rev:
        return True
    if (event.event_name != last_rev.event_name
            or event.sub_event_name != last_rev.sub_event_name):
        return True
    return await _files_differ_between(db, event.id, 0, event.id, event.current_media_version)


async def _get_files_for_version(
    db: AsyncSession, event_id: int, version: int
) -> list[EventMediaItem]:
    result = await db.execute(
        select(EventMediaItem).where(
            EventMediaItem.event_id == event_id,
            EventMediaItem.media_versions.any(version),
        ).order_by(EventMediaItem.sort_order)
    )
    return list(result.scalars().all())


async def _get_names_for_version(
    db: AsyncSession, event_id: int, version: int
) -> set[str]:
    result = await db.execute(
        select(EventMediaItem.original_filename).where(
            EventMediaItem.event_id == event_id,
            EventMediaItem.media_versions.any(version),
        )
    )
    return set(result.scalars().all())


async def _files_differ_between(
    db: AsyncSession,
    event_id_a: int, version_a: int,
    event_id_b: int, version_b: int,
) -> bool:
    names_a = await _get_names_for_version(db, event_id_a, version_a)
    names_b = await _get_names_for_version(db, event_id_b, version_b)
    return names_a != names_b


async def _sync_staging(
    db: AsyncSession, event: Event, selected_names: list[str]
) -> None:
    """Make staging (version 0) match exactly what FE sent."""
    desired = set(selected_names)

    all_files = (await db.execute(
        select(EventMediaItem).where(EventMediaItem.event_id == event.id)
    )).scalars().all()

    for f in all_files:
        in_staging = 0 in f.media_versions
        wanted = f.original_filename in desired

        if wanted and not in_staging:
            f.media_versions = [*f.media_versions, 0]
        elif not wanted and in_staging:
            f.media_versions = [v for v in f.media_versions if v != 0]
