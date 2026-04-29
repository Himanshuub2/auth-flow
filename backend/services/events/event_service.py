import logging

from fastapi import HTTPException, status
from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from models.events.event import Event, EventRevision, EventStatus
from models.events.event_media_item import EventMediaItem, FileType
from models.events.user import User
from schemas.events.event import (
    EventListItemOut,
    EventOut,
    EventPreviewMediaItem,
    EventSavePayload,
    FileMetadataIn,
    MediaFileSummary,
)
from storage import get_storage
from utils.applicability import validate_applicability_refs

logger = logging.getLogger(__name__)

PREVIEW_MEDIA_LIMIT = 6

# Per-event media limits
MAX_EVENT_IMAGES = 50
MAX_EVENT_VIDEOS = 8
MAX_EVENT_THUMBNAILS = 8
MAX_EVENT_IMAGE_SIZE_BYTES = 10 * 1024 * 1024    # 10 MB
MAX_EVENT_VIDEO_SIZE_BYTES = 500 * 1024 * 1024   # 500 MB


async def save_event(
    db: AsyncSession,
    user_id: str,
    payload: EventSavePayload,
    *,
    event_id: int | None = None,
) -> Event:
    validate_applicability_refs(payload.applicability_type, payload.applicability_refs)
    is_new = event_id is None

    if is_new:
        event = Event(created_by=user_id)
        db.add(event)
        await db.flush()
    else:
        event = await get_event(db, event_id)
        event.updated_by = user_id

        if event.status == EventStatus.ACTIVE and payload.status == EventStatus.DRAFT:
            event = await _get_or_create_draft(db, event, user_id)
        elif event.status == EventStatus.ACTIVE and payload.status == EventStatus.ACTIVE:
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

    if payload.selected_file_ids is not None:
        await _sync_media_from_metadata(
            db,
            event,
            payload.file_metadata or [],
            selected_file_ids=payload.selected_file_ids,
        )
    elif payload.file_metadata is not None:
        await _sync_media_from_metadata(db, event, payload.file_metadata)

    if payload.status == EventStatus.ACTIVE:
        await _validate_active_event_name_uniqueness(
            db,
            event_name=event.event_name,
            sub_event_name=event.sub_event_name,
            exclude_id=event.id,
            allow_replaced_active_id=event.replaces_document_id,
        )
        if event.replaces_document_id is not None:
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


def _compute_media_versions(file_id: int, event: Event) -> list[int]:
    """Compute the media_versions list for a file based on staging and revisions."""
    versions: list[int] = []
    if file_id in (event.staging_file_ids or []):
        versions.append(0)
    for rev in (event.revisions or []):
        if file_id in (rev.file_ids or []):
            versions.append(rev.media_version)
    return sorted(set(versions))


def _build_media_summary(f: EventMediaItem, event: Event) -> MediaFileSummary:
    """Build a MediaFileSummary with fresh read SAS URLs from stored blob paths."""
    storage = get_storage()
    return MediaFileSummary(
        id=f.id,
        file_url=storage.get_read_url(f.file_url),
        blob_path=f.file_url,
        original_filename=f.original_filename,
        media_versions=_compute_media_versions(f.id, event),
        file_type=f.file_type,
        thumbnail_url=storage.get_read_url(f.thumbnail_url) if f.thumbnail_url else None,
        thumbnail_blob_path=f.thumbnail_url,
        caption=f.caption,
        description=f.description,
    )


async def get_event_detail_for_revision(db: AsyncSession, event_id: int) -> EventOut:
    """Item detail: full Event + User.username only; media filtered by current version."""
    updater = aliased(User)
    deactivator = aliased(User)
    row = await db.execute(
        select(
            Event,
            User.username.label("created_by_name"),
            updater.username.label("updated_by_name"),
            deactivator.username.label("deactivated_by_name"),
        )
        .join(User, Event.created_by == User.staff_id)
        .outerjoin(updater, Event.updated_by == updater.staff_id)
        .outerjoin(deactivator, Event.deactivated_by == deactivator.staff_id)
        .where(Event.id == event_id)
    )
    one = row.one_or_none()
    if not one:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    event, created_by_name, updated_by_name, deactivated_by_name = one[0], one[1], one[2], one[3]
    ver = event.current_media_version

    file_ids = await _get_file_ids_for_version(db, event, ver if ver > 0 else 0)
    all_files = await _get_all_files(db, event_id)
    file_by_id = {f.id: f for f in all_files}
    version_files = [file_by_id[fid] for fid in file_ids if fid in file_by_id]

    files = [_build_media_summary(f, event) for f in version_files]
    updated_by_display = (
        f"{updated_by_name} ({event.updated_by})"
        if event.updated_by and updated_by_name
        else event.updated_by
    )
    deactivated_by_display = (
        f"{deactivated_by_name} ({event.deactivated_by})"
        if event.deactivated_by and deactivated_by_name
        else event.deactivated_by
    )

    lc = int(getattr(event, "like_count", 0) or 0)
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
        updated_by=updated_by_display,
        created_at=event.created_at,
        updated_at=event.updated_at,
        change_remarks=event.change_remarks,
        deactivate_remarks=event.deactivate_remarks,
        deactivated_by=deactivated_by_display,
        deactivated_at=event.deactivated_at,
        like_count=lc,
        liked_by_me=False,
        files=files,
    )


def build_event_out(event: Event, *, liked_by_me: bool = False) -> EventOut:
    """Build EventOut from loaded Event (with media_items and creator)."""
    ver = event.current_media_version
    target_ver = ver if ver > 0 else 0
    target_file_ids = _get_file_ids_for_version_sync(event, target_ver)
    file_by_id = {m.id: m for m in event.media_items}
    files = [
        _build_media_summary(m, event)
        for fid in target_file_ids
        if (m := file_by_id.get(fid)) is not None
    ]
    lc = int(getattr(event, "like_count", 0) or 0)
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
        created_by_name=event.creator.username,
        created_at=event.created_at,
        updated_at=event.updated_at,
        change_remarks=event.change_remarks,
        deactivate_remarks=event.deactivate_remarks,
        deactivated_at=event.deactivated_at,
        like_count=lc,
        liked_by_me=liked_by_me,
        files=files,
    )


async def get_file_ids_for_event_list_card(db: AsyncSession, event: Event) -> list[int]:
    """Ordered file IDs for the event's current published/staging view (no in-memory revisions)."""
    ver = event.current_media_version
    target_ver = ver if ver > 0 else 0
    return await _get_file_ids_for_version(db, event, target_ver)


def build_event_list_card(
    event: Event, file_ids: list[int], *, liked_by_me: bool
) -> EventListItemOut:
    """Card row for GET /events: preview media and like fields."""
    total = len(file_ids)
    preview_ids = file_ids[:PREVIEW_MEDIA_LIMIT]
    file_by_id = {m.id: m for m in event.media_items}
    storage = get_storage()
    preview_media: list[EventPreviewMediaItem] = []
    for fid in preview_ids:
        m = file_by_id.get(fid)
        if m is None:
            continue
        preview_media.append(
            EventPreviewMediaItem(
                id=m.id,
                file_type=m.file_type,
                thumbnail_url=storage.get_read_url(m.thumbnail_url) if m.thumbnail_url else None,
                file_url=storage.get_read_url(m.file_url),
            )
        )
    remaining = max(0, total - PREVIEW_MEDIA_LIMIT)
    lc = int(getattr(event, "like_count", 0) or 0)
    return EventListItemOut(
        id=event.id,
        event_name=event.event_name,
        sub_event_name=event.sub_event_name,
        event_dates=event.event_dates,
        description=event.description,
        tags=event.tags,
        like_count=lc,
        liked_by_me=liked_by_me,
        preview_media=preview_media,
        remaining_media_count=remaining,
    )


async def list_events(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status_filter: EventStatus | None = None,
    search: str | None = None,
) -> tuple[list[Event], int]:
    effective_status = status_filter if status_filter is not None else EventStatus.ACTIVE

    query = select(Event).where(Event.status == effective_status)
    count_query = select(func.count()).select_from(Event).where(Event.status == effective_status)

    if search and search.strip():
        term = f"%{search.strip()}%"
        search_cond = or_(
            Event.event_name.ilike(term),
            func.coalesce(Event.description, "").ilike(term),
            func.coalesce(cast(Event.tags, Text), "").ilike(term),
        )
        query = query.where(search_cond)
        count_query = count_query.where(search_cond)

    total = (await db.execute(count_query)).scalar() or 0
    query = (
        query.options(
            selectinload(Event.creator),
            selectinload(Event.media_items),
        )
        .order_by(Event.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    events = list((await db.execute(query)).scalars().all())
    return events, total


async def toggle_event_status(
    db: AsyncSession, event_id: int, deactivated_by: str, deactivate_remarks: str | None = None
) -> Event:
    event = await get_event(db, event_id)
    if event.status == EventStatus.ACTIVE:
        if not deactivate_remarks or not deactivate_remarks.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Deactivation remarks are required when deactivating an event",
            )
        event.status = EventStatus.INACTIVE
        event.deactivate_remarks = deactivate_remarks.strip()
        event.deactivated_at = func.now()
        event.deactivated_by = deactivated_by
    elif event.status == EventStatus.INACTIVE:
        await _validate_active_event_name_uniqueness(
            db,
            event_name=event.event_name,
            sub_event_name=event.sub_event_name,
            exclude_id=event.id,
        )
        event.status = EventStatus.ACTIVE
        event.deactivate_remarks = None
        event.deactivated_at = None
        event.deactivated_by = None
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only ACTIVE/INACTIVE events can be toggled",
        )
    event.updated_by = deactivated_by
    await db.flush()
    await db.refresh(event)
    return event


async def create_draft_from_event(db: AsyncSession, parent_event_id: int, user_id: str) -> Event:
    parent = await get_event(db, parent_event_id)
    if parent.status != EventStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Can only create drafts from active events")
    draft = await _get_or_create_draft(db, parent, user_id)
    await db.refresh(draft)
    return draft


async def _get_or_create_draft(db: AsyncSession, parent: Event, user_id: str) -> Event:
    existing = (await db.execute(
        select(Event).where(
            Event.replaces_document_id == parent.id,
            Event.status == EventStatus.DRAFT,
        )
    )).scalar_one_or_none()
    if existing:
        return existing

    parent_file_ids = await _get_file_ids_for_version(db, parent, parent.current_media_version)

    parent_files = await _get_all_files(db, parent.id)
    parent_file_by_id = {f.id: f for f in parent_files}

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

    new_staging_ids: list[int] = []
    for fid in parent_file_ids:
        pf = parent_file_by_id.get(fid)
        if not pf:
            continue
        new_file = EventMediaItem(
            event_id=draft.id,
            file_type=pf.file_type,
            file_url=pf.file_url,
            thumbnail_url=pf.thumbnail_url,
            caption=pf.caption,
            description=pf.description,
            sort_order=pf.sort_order,
            file_size_bytes=pf.file_size_bytes,
            original_filename=pf.original_filename,
        )
        db.add(new_file)
        await db.flush()
        new_staging_ids.append(new_file.id)

    draft.staging_file_ids = new_staging_ids
    await db.flush()
    return draft


# -- publish ---------------------------------------------------------------

async def _publish_event(db: AsyncSession, event: Event) -> None:
    if event.current_media_version == 0:
        event.current_media_version = 1
        event.current_revision_number = 0
    else:
        last_rev = _find_latest_revision(event)
        if not last_rev:
            event.current_media_version += 1
            event.current_revision_number = 0
        elif _names_changed_vs_revision(event, last_rev) or await _files_differ_between(
            db, event, 0, event, event.current_media_version
        ):
            event.current_media_version += 1
            event.current_revision_number = 0
        elif _non_name_metadata_changed_vs_revision(event, last_rev):
            event.current_revision_number += 1
        else:
            # Only caption/description on media items changed
            event.staging_file_ids = []
            event.status = EventStatus.ACTIVE
            return

    published_file_ids = list(event.staging_file_ids or [])

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
        file_ids=published_file_ids,
        created_by=event.created_by,
    ))

    event.staging_file_ids = []
    event.status = EventStatus.ACTIVE


async def _publish_draft(db: AsyncSession, draft: Event) -> Event:
    result = await db.execute(
        select(Event)
        .where(Event.id == draft.replaces_document_id)
        .options(selectinload(Event.revisions))
    )
    parent = result.scalar_one_or_none()
    if not parent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent event not found")

    last_rev = _find_latest_revision(parent)
    if not last_rev:
        media_bump = True
        meta_only = False
    else:
        name_changed = _names_changed_vs_revision(draft, last_rev)
        files_changed = await _files_differ_between(
            db, draft, 0, parent, parent.current_media_version
        )
        media_bump = name_changed or files_changed
        meta_only = _non_name_metadata_changed_vs_revision(draft, last_rev)

    if media_bump:
        draft.current_media_version = parent.current_media_version + 1
        draft.current_revision_number = 0
    elif meta_only:
        draft.current_media_version = parent.current_media_version
        draft.current_revision_number = parent.current_revision_number + 1
    else:
        draft.current_media_version = parent.current_media_version
        draft.current_revision_number = parent.current_revision_number

    published_file_ids = list(draft.staging_file_ids or [])

    for rev in parent.revisions:
        rev.event_id = draft.id

    parent_files = await _get_all_files(db, parent.id)
    for f in parent_files:
        f.event_id = draft.id

    if media_bump or meta_only:
        db.add(EventRevision(
            event_id=draft.id,
            media_version=draft.current_media_version,
            revision_number=draft.current_revision_number,
            event_name=draft.event_name,
            sub_event_name=draft.sub_event_name,
            event_dates=draft.event_dates,
            description=draft.description,
            tags=draft.tags,
            change_remarks=draft.change_remarks,
            file_ids=published_file_ids,
            created_by=draft.created_by,
        ))
    elif last_rev is not None:
        last_rev.file_ids = list(published_file_ids)

    parent.status = EventStatus.INACTIVE
    draft.status = EventStatus.ACTIVE
    draft.replaces_document_id = None
    draft.staging_file_ids = []

    await db.flush()
    await db.refresh(draft)
    return draft


# -- helpers ---------------------------------------------------------------

def _find_latest_revision(event: Event) -> EventRevision | None:
    if not event.revisions:
        return None
    return max(event.revisions, key=lambda r: (r.media_version, r.revision_number))


def _names_changed_vs_revision(event: Event, last_rev: EventRevision) -> bool:
    return (
        event.event_name != last_rev.event_name
        or event.sub_event_name != last_rev.sub_event_name
    )


def _non_name_metadata_changed_vs_revision(event: Event, last_rev: EventRevision) -> bool:
    return (
        event.event_dates != last_rev.event_dates
        or event.description != last_rev.description
        or event.tags != last_rev.tags
        or event.change_remarks != last_rev.change_remarks
    )


async def _get_all_files(db: AsyncSession, event_id: int) -> list[EventMediaItem]:
    result = await db.execute(
        select(EventMediaItem)
        .where(EventMediaItem.event_id == event_id)
        .order_by(EventMediaItem.sort_order)
    )
    return list(result.scalars().all())


def _get_file_ids_for_version_sync(event: Event, version: int) -> list[int]:
    """Sync version: get file IDs for a version from loaded event (staging or revisions)."""
    if version == 0:
        return list(event.staging_file_ids or [])
    for rev in (event.revisions or []):
        if rev.media_version == version:
            return list(rev.file_ids or [])
    return list(event.staging_file_ids or [])


async def _get_file_ids_for_version(db: AsyncSession, event: Event, version: int) -> list[int]:
    """Get file IDs for a version. For staging (0), use event.staging_file_ids. For published, find revision."""
    if version == 0:
        return list(event.staging_file_ids or [])
    result = await db.execute(
        select(EventRevision.file_ids)
        .where(
            EventRevision.event_id == event.id,
            EventRevision.media_version == version,
        )
        .order_by(EventRevision.revision_number.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return list(row)
    return list(event.staging_file_ids or [])


async def _get_names_for_version(
    db: AsyncSession, event: Event, version: int,
) -> set[str]:
    file_ids = await _get_file_ids_for_version(db, event, version)
    if not file_ids:
        return set()
    all_files = await _get_all_files(db, event.id)
    file_by_id = {f.id: f for f in all_files}
    return {file_by_id[fid].original_filename for fid in file_ids if fid in file_by_id}


async def _files_differ_between(
    db: AsyncSession,
    event_a: Event, version_a: int,
    event_b: Event, version_b: int,
) -> bool:
    names_a = await _get_names_for_version(db, event_a, version_a)
    names_b = await _get_names_for_version(db, event_b, version_b)
    return names_a != names_b


def _validate_event_media_limits(
    file_metadata: list[FileMetadataIn],
    existing_files: list[EventMediaItem],
    selected_file_ids: list[int] | None,
) -> None:
    """
    Validate per-event media limits before any rows are created.
    Final staging set = kept existing files (selected_file_ids) + ALL file_metadata.
    """
    existing_id_set = {f.id for f in existing_files}

    kept_files: list[EventMediaItem] = []
    if selected_file_ids is not None:
        kept_id_set = {fid for fid in selected_file_ids if fid in existing_id_set}
        kept_files = [f for f in existing_files if f.id in kept_id_set]

    total_images = sum(1 for f in kept_files if f.file_type == FileType.IMAGE)
    total_videos = sum(1 for f in kept_files if f.file_type == FileType.VIDEO)
    total_thumbnails = sum(1 for f in kept_files if f.thumbnail_url)

    for meta in file_metadata:
        if meta.file_type == FileType.IMAGE:
            total_images += 1
            if meta.file_size_bytes > MAX_EVENT_IMAGE_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Image '{meta.original_filename}' exceeds the {MAX_EVENT_IMAGE_SIZE_BYTES // (1024 * 1024)}MB limit",
                )
        elif meta.file_type == FileType.VIDEO:
            total_videos += 1
            if meta.file_size_bytes > MAX_EVENT_VIDEO_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Video '{meta.original_filename}' exceeds the {MAX_EVENT_VIDEO_SIZE_BYTES // (1024 * 1024)}MB limit",
                )
        if meta.thumbnail_blob_path:
            total_thumbnails += 1

    if total_images > MAX_EVENT_IMAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_EVENT_IMAGES} images allowed per event",
        )
    if total_videos > MAX_EVENT_VIDEOS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_EVENT_VIDEOS} videos allowed per event",
        )
    if total_thumbnails > MAX_EVENT_THUMBNAILS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_EVENT_THUMBNAILS} thumbnails allowed per event",
        )


async def _sync_media_from_metadata(
    db: AsyncSession,
    event: Event,
    file_metadata: list[FileMetadataIn],
    *,
    selected_file_ids: list[int] | None = None,
) -> None:
    """
    Sync EventMediaItem rows from FE-provided file_metadata (blob paths).

    **Create** (selected_file_ids is None):
        staging = all file_metadata items (new rows created from blob paths).

    **Update** (selected_file_ids provided):
        staging = selected_file_ids (existing files to keep)
                + all files referenced by file_metadata.
        This means metadata can append files even when selected_file_ids is empty.
    """
    existing_files = await _get_all_files(db, event.id)
    existing_id_set = {f.id for f in existing_files}

    _validate_event_media_limits(file_metadata, existing_files, selected_file_ids)

    all_metadata_ids: list[int] = []

    for idx, meta in enumerate(file_metadata):
        item = EventMediaItem(
            event_id=event.id,
            file_type=meta.file_type,
            file_url=meta.blob_path,
            thumbnail_url=meta.thumbnail_blob_path,
            caption=meta.caption,
            description=meta.description,
            sort_order=meta.sort_order if meta.sort_order else idx,
            file_size_bytes=meta.file_size_bytes,
            original_filename=meta.original_filename,
        )
        db.add(item)
        await db.flush()
        all_metadata_ids.append(item.id)

    if selected_file_ids is None:
        event.staging_file_ids = all_metadata_ids
        logger.debug("Synced %d media items for event %s from metadata", len(file_metadata), event.id)
        return

    kept_id_set = {fid for fid in selected_file_ids if fid in existing_id_set}
    desired_staging_ids: list[int] = []
    seen_ids: set[int] = set()

    for fid in selected_file_ids:
        if fid in existing_id_set and fid not in seen_ids:
            desired_staging_ids.append(fid)
            seen_ids.add(fid)

    for fid in all_metadata_ids:
        if fid not in seen_ids:
            desired_staging_ids.append(fid)
            seen_ids.add(fid)

    if event.status == EventStatus.DRAFT:
        removed = [f for f in existing_files if f.id not in kept_id_set]
        if removed:
            storage = get_storage()
            for f in removed:
                if f.file_url:
                    await storage.delete(f.file_url)
                if f.thumbnail_url:
                    await storage.delete(f.thumbnail_url)
                await db.delete(f)
            logger.debug(
                "Deleted %d removed media items (DB + blob) for draft event %s",
                len(removed), event.id,
            )

    event.staging_file_ids = desired_staging_ids
    logger.debug("Synced %d media items for event %s (kept + metadata)", len(desired_staging_ids), event.id)


async def _validate_active_event_name_uniqueness(
    db: AsyncSession,
    *,
    event_name: str,
    sub_event_name: str | None,
    exclude_id: int | None = None,
    allow_replaced_active_id: int | None = None,
) -> None:
    normalized_event_name = (event_name or "").strip().lower()
    normalized_sub_event_name = (sub_event_name or "").strip().lower()
    stmt = (
        select(Event.id)
        .where(
            Event.status == EventStatus.ACTIVE,
            func.lower(func.trim(Event.event_name)) == normalized_event_name,
            func.lower(func.trim(func.coalesce(Event.sub_event_name, ""))) == normalized_sub_event_name,
        )
        .order_by(Event.id.asc())
        .limit(1)
    )
    if exclude_id is not None:
        stmt = stmt.where(Event.id != exclude_id)
    if allow_replaced_active_id is not None:
        stmt = stmt.where(Event.id != allow_replaced_active_id)

    existing_id = (await db.execute(stmt)).scalar_one_or_none()
    if existing_id is None:
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "Active event with same event_name and sub_event_name "
            "already exists"
        ),
    )
