import logging

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.events.event import Event, EventRevision, EventStatus
from app.models.events.event_media_item import EventMediaItem
from app.models.events.user import User
from app.schemas.events.event import EventOut, EventSavePayload, FileMetadataIn, MediaFileSummary
from app.services.events.media_service import upload_files

logger = logging.getLogger(__name__)


async def save_event(
    db: AsyncSession,
    user_id: int,
    payload: EventSavePayload,
    *,
    event_id: int | None = None,
    files: list[UploadFile] | None = None,
) -> Event:
    is_new = event_id is None

    if is_new:
        # Brand new event - no relation with any existing record
        event = Event(created_by=user_id)
        db.add(event)
        await db.flush()
    else:
        event = await get_event(db, event_id)

        if event.status == EventStatus.ACTIVE and payload.status == EventStatus.DRAFT:
            # Edit active → save as draft → creates a new draft entry linked to parent
            event = await _get_or_create_draft(db, event, user_id)
        elif event.status == EventStatus.ACTIVE and payload.status == EventStatus.ACTIVE:
            # Re-publishing a published event directly: require change_remarks
            if not payload.change_remarks or not payload.change_remarks.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="change_remarks is required when activating an edit",
                )

    event.event_name = payload.event_name
    event.sub_event_name = payload.sub_event_name
    event.event_dates = payload.event_dates
    event.description = payload.description
    event.tags = payload.tags
    event.applicability_type = payload.applicability_type
    event.applicability_refs = payload.applicability_refs
    event.change_remarks = payload.change_remarks

    uploaded_names: list[str] = []
    if files:
        uploaded = await upload_files(db, event.id, files, payload.file_metadata)
        uploaded_names = [f.original_filename for f in uploaded]

    if payload.selected_filenames is not None:
        all_names = list(dict.fromkeys([*payload.selected_filenames, *uploaded_names]))
        await _sync_staging(db, event, all_names)

    if payload.file_metadata:
        await _apply_file_metadata(db, event.id, payload.file_metadata)

    if payload.status == EventStatus.ACTIVE:
        if event.replaces_document_id is not None:
            # Publishing a draft record → deactivate the parent
            event = await _publish_draft(db, event)
        else:
            await _publish_event(db, event)
    else:
        event.status = EventStatus.DRAFT

    await db.flush()
    await db.refresh(event)
    return await get_event_with_relations(db, event.id)


async def get_event(db: AsyncSession, event_id: int) -> Event:
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


async def get_event_with_relations(db: AsyncSession, event_id: int) -> Event:
    """Load full Event ORM with media_items and creator (for routers that need it)."""
    result = await db.execute(
        select(Event)
        .where(Event.id == event_id)
        .options(selectinload(Event.media_items), selectinload(Event.creator))
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


async def get_event_detail_for_revision(db: AsyncSession, event_id: int) -> EventOut:
    """Item detail: full Event + User.full_name only; media: id, file_url, original_filename, media_versions, file_type."""
    row = await db.execute(
        select(Event, User.full_name.label("created_by_name"))
        .join(User, Event.created_by == User.id)
        .where(Event.id == event_id)
    )
    one = row.one_or_none()
    if not one:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    event, created_by_name = one[0], one[1]
    ver = event.current_media_version
    target_ver = ver if ver > 0 else 0

    media_rows = await db.execute(
        select(
            EventMediaItem.id,
            EventMediaItem.file_url,
            EventMediaItem.original_filename,
            EventMediaItem.media_versions,
            EventMediaItem.file_type,
        )
        .where(
            EventMediaItem.event_id == event_id,
            EventMediaItem.media_versions.any(target_ver),
        )
        .order_by(EventMediaItem.sort_order)
    )
    files = [
        MediaFileSummary(
            id=r.id,
            file_url=r.file_url,
            original_filename=r.original_filename,
            media_versions=r.media_versions,
            file_type=r.file_type,
            thumbnail_url=None,
            caption=None,
            description=None,
        )
        for r in media_rows.all()
    ]

    return EventOut(
        id=event.id,
        event_name=event.event_name,
        sub_event_name=event.sub_event_name,
        event_dates=event.event_dates,
        description=event.description,
        tags=event.tags,
        current_media_version=ver,
        current_revision_number=event.current_revision_number,
        version_display=f"{ver}.{event.current_revision_number}",
        status=event.status,
        applicability_type=event.applicability_type,
        applicability_refs=event.applicability_refs,
        replaces_document_id=event.replaces_document_id,
        created_by=event.created_by,
        created_by_name=created_by_name,
        created_at=event.created_at,
        updated_at=event.updated_at,
        change_remarks=event.change_remarks,
        deactivate_remarks=event.deactivate_remarks,
        deactivated_at=event.deactivated_at,
        files=files,
    )


def build_event_out(event: Event) -> EventOut:
    """Build EventOut from loaded Event (with media_items and creator)."""
    ver = event.current_media_version
    target_ver = ver if ver > 0 else 0
    files = [
        MediaFileSummary.model_validate(m)
        for m in event.media_items
        if target_ver in m.media_versions
    ]
    return EventOut(
        id=event.id,
        event_name=event.event_name,
        sub_event_name=event.sub_event_name,
        event_dates=event.event_dates,
        description=event.description,
        tags=event.tags,
        current_media_version=ver,
        current_revision_number=event.current_revision_number,
        version_display=f"{ver}.{event.current_revision_number}",
        status=event.status,
        applicability_type=event.applicability_type,
        applicability_refs=event.applicability_refs,
        replaces_document_id=event.replaces_document_id,
        created_by=event.created_by,
        created_by_name=event.creator.full_name,
        created_at=event.created_at,
        updated_at=event.updated_at,
        change_remarks=event.change_remarks,
        deactivate_remarks=event.deactivate_remarks,
        deactivated_at=event.deactivated_at,
        files=files,
    )


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
        query.options(selectinload(Event.creator))
        .order_by(Event.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    events = list((await db.execute(query)).scalars().all())
    return events, total


async def delete_event(db: AsyncSession, event_id: int, deactivate_remarks: str, deactivated_by: int) -> None:
    event = await get_event(db, event_id)
    event.deactivate_remarks = deactivate_remarks
    event.deactivated_at = func.now()
    event.deactivated_by = deactivated_by
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
    if parent.status != EventStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Can only create drafts from active events")
    draft = await _get_or_create_draft(db, parent, user_id)
    await db.refresh(draft)
    return draft


async def _get_or_create_draft(db: AsyncSession, parent: Event, user_id: int) -> Event:
    existing = (await db.execute(
        select(Event).where(
            Event.replaces_document_id == parent.id,
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
        replaces_document_id=parent.id,
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
        change_remarks=event.change_remarks,
        created_by=event.created_by,
    ))
    event.status = EventStatus.ACTIVE


async def _publish_draft(db: AsyncSession, draft: Event) -> Event:
    parent = await get_event(db, draft.replaces_document_id)

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
        change_remarks=draft.change_remarks,
        created_by=draft.created_by,
    ))

    parent.status = EventStatus.INACTIVE
    draft.status = EventStatus.ACTIVE
    draft.replaces_document_id = None

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


async def _apply_file_metadata(
    db: AsyncSession, event_id: int, file_metadata: list[FileMetadataIn]
) -> None:
    """Update caption and description for existing media items."""
    meta_by_name = {m.original_filename: m for m in file_metadata}
    if not meta_by_name:
        return
    result = await db.execute(
        select(EventMediaItem).where(EventMediaItem.event_id == event_id)
    )
    for item in result.scalars().all():
        meta = meta_by_name.get(item.original_filename)
        if not meta:
            continue
        item.caption = meta.caption
        item.description = meta.description
    logger.debug("Applied file_metadata for %d items on event %s", len(meta_by_name), event_id)
