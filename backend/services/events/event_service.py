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
    validate_applicability_refs(
        payload.applicability_type,
        payload.applicability_refs,
        allow_division=False,
    )
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

    # if not is_new and payload.version != float(event.version):
    #     await _validate_version_unique(db, payload.version, exclude_id=event.id)

    event.event_name = payload.event_name
    event.sub_event_name = payload.sub_event_name
    event.event_dates = payload.event_dates
    event.description = payload.description
    event.tags = payload.tags
    event.applicability_type = payload.applicability_type
    event.applicability_refs = payload.applicability_refs
    event.change_remarks = payload.change_remarks
    event.version = payload.version

    if payload.file_metadata is not None:
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
        .options(selectinload(Event.media_items), selectinload(Event.creator), selectinload(Event.revisions))
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


def _compute_media_versions(file_id: int, event: Event) -> list[int]:
    """Compute which revision_numbers a file appears in (0 = staging)."""
    versions: list[int] = []
    if file_id in (event.staging_file_ids or []):
        versions.append(0)
    for rev in (event.revisions or []):
        if file_id in (rev.file_ids or []):
            versions.append(rev.revision_number)
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

    file_ids = await _get_current_file_ids(db, event)
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
        version=event.version,
        revision=event.revision,
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
    target_file_ids = _get_current_file_ids_sync(event)
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
        version=event.version,
        revision=event.revision,
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
    return await _get_current_file_ids(db, event)


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

    parent_file_ids = await _get_current_file_ids(db, parent)

    parent_files = await _get_all_files(db, parent.id)
    parent_file_by_id = {f.id: f for f in parent_files}
    draft = Event(
        event_name=parent.event_name,
        sub_event_name=parent.sub_event_name,
        event_dates=parent.event_dates,
        description=parent.description,
        tags=parent.tags,
        version=parent.version,
        revision=parent.revision,
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
    last_rev = await _get_latest_revision(db, event.id)
    if last_rev:
        metadata_changed = (
            _names_changed_vs_revision(event, last_rev)
            or _non_name_metadata_changed_vs_revision(event, last_rev)
        )
        files_changed = await _staging_files_differ_from_revision(db, event, last_rev)
        if metadata_changed or files_changed:
            event.revision += 1
        else:
            event.staging_file_ids = []
            event.status = EventStatus.ACTIVE
            return

    published_file_ids = list(event.staging_file_ids or [])

    db.add(EventRevision(
        event_id=event.id,
        media_version=event.version,
        revision_number=event.revision,
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
    any_changes = True
    if last_rev:
        metadata_changed = (
            _names_changed_vs_revision(draft, last_rev)
            or _non_name_metadata_changed_vs_revision(draft, last_rev)
        )
        files_changed = await _staging_files_differ_from_revision(db, draft, last_rev)
        any_changes = metadata_changed or files_changed

    if any_changes:
        draft.revision = parent.revision + 1
    else:
        draft.revision = parent.revision

    published_file_ids = list(draft.staging_file_ids or [])

    for rev in parent.revisions:
        rev.event_id = draft.id

    parent_files = await _get_all_files(db, parent.id)
    for f in parent_files:
        f.event_id = draft.id

    if any_changes:
        db.add(EventRevision(
            event_id=draft.id,
            media_version=1,
            revision_number=draft.revision,
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


async def _get_latest_revision(db: AsyncSession, event_id: int) -> EventRevision | None:
    result = await db.execute(
        select(EventRevision)
        .where(EventRevision.event_id == event_id)
        .order_by(EventRevision.revision_number.desc(), EventRevision.media_version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


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
        or event.version != last_rev.media_version
    )


async def _get_all_files(db: AsyncSession, event_id: int) -> list[EventMediaItem]:
    result = await db.execute(
        select(EventMediaItem)
        .where(EventMediaItem.event_id == event_id)
        .order_by(EventMediaItem.sort_order)
    )
    return list(result.scalars().all())


def _get_current_file_ids_sync(event: Event) -> list[int]:
    """Get file IDs for the event's current state from loaded relations."""
    if event.status != EventStatus.DRAFT and event.revisions:
        latest = max(event.revisions, key=lambda r: (r.revision_number, r.media_version))
        return list(latest.file_ids or [])
    return list(event.staging_file_ids or [])


async def _get_current_file_ids(db: AsyncSession, event: Event) -> list[int]:
    """Get file IDs for the event's current state. Active -> latest revision; Draft -> staging."""
    if event.status != EventStatus.DRAFT:
        result = await db.execute(
            select(EventRevision.file_ids)
            .where(EventRevision.event_id == event.id)
            .order_by(EventRevision.revision_number.desc(), EventRevision.media_version.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return list(row)
    return list(event.staging_file_ids or [])


async def _get_media_signatures_from_file_ids(
    db: AsyncSession, event_id: int, file_ids: list[int],
) -> list[tuple]:
    if not file_ids:
        return []
    all_files = await _get_all_files(db, event_id)
    file_by_id = {f.id: f for f in all_files}
    signatures: list[tuple] = []
    for fid in file_ids:
        media = file_by_id.get(fid)
        if media is None:
            continue
        signatures.append(
            (
                media.original_filename,
                media.file_type.value,
                media.caption,
                media.description,
                media.sort_order,
                media.file_url,
                media.thumbnail_url,
            )
        )
    return signatures


async def _staging_files_differ_from_revision(
    db: AsyncSession, event: Event, last_rev: EventRevision,
) -> bool:
    staging_signatures = await _get_media_signatures_from_file_ids(
        db, event.id, list(event.staging_file_ids or []),
    )
    revision_signatures = await _get_media_signatures_from_file_ids(
        db, event.id, list(last_rev.file_ids or []),
    )
    return staging_signatures != revision_signatures


async def _validate_version_unique(db: AsyncSession, version: float, *, exclude_id: int | None = None) -> None:
    stmt = select(Event.id).where(Event.version == version).limit(1)
    if exclude_id is not None:
        stmt = stmt.where(Event.id != exclude_id)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Version {version} already exists for another event",
        )


def _validate_event_media_limits(final_files: list[EventMediaItem], new_files: list[FileMetadataIn]) -> None:
    """
    Validate per-event media limits for the final file composition.
    """
    total_images = sum(1 for f in final_files if f.file_type == FileType.IMAGE)
    total_videos = sum(1 for f in final_files if f.file_type == FileType.VIDEO)
    total_thumbnails = sum(1 for f in final_files if f.thumbnail_url)

    for meta in new_files:
        if meta.file_type == FileType.IMAGE and meta.file_size_bytes is not None:
            if meta.file_size_bytes > MAX_EVENT_IMAGE_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Image '{meta.original_filename}' exceeds the {MAX_EVENT_IMAGE_SIZE_BYTES // (1024 * 1024)}MB limit",
                )
        elif meta.file_type == FileType.VIDEO and meta.file_size_bytes is not None:
            if meta.file_size_bytes > MAX_EVENT_VIDEO_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Video '{meta.original_filename}' exceeds the {MAX_EVENT_VIDEO_SIZE_BYTES // (1024 * 1024)}MB limit",
                )

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
) -> None:
    """
    Sync event files based on the payload.

    - id present  → keep that file, update caption/description/etc.
    - id is null  → create a new file
    - existing files not in payload → remove them

    For drafts of active events the FE may send parent file IDs.
    We resolve them to existing draft copies (made by _get_or_create_draft).
    """
    existing_files = await _get_all_files(db, event.id)
    existing_by_id: dict[int, EventMediaItem] = {f.id: f for f in existing_files}

    # For drafts, load parent files so we can resolve parent IDs
    parent_by_id: dict[int, EventMediaItem] = {}
    parent_blob_paths: set[str] = set()
    if event.replaces_document_id is not None:
        parent_files = await _get_all_files(db, event.replaces_document_id)
        parent_by_id = {f.id: f for f in parent_files}
        for pf in parent_files:
            if pf.file_url:
                parent_blob_paths.add(pf.file_url)
            if pf.thumbnail_url:
                parent_blob_paths.add(pf.thumbnail_url)

    desired_ids: list[int] = []
    seen: set[int] = set()
    new_file_metas: list[FileMetadataIn] = []

    for idx, meta in enumerate(file_metadata):
        order = meta.sort_order or idx

        if meta.id is not None:
            file = existing_by_id.get(meta.id)

            # Parent file ID → find draft copy by matching file_url
            if file is None and meta.id in parent_by_id:
                pf = parent_by_id[meta.id]
                file = next(
                    (f for f in existing_files if f.file_url == pf.file_url),
                    None,
                )
                if file is None:
                    file = EventMediaItem(
                        event_id=event.id,
                        file_type=pf.file_type,
                        file_url=pf.file_url,
                        thumbnail_url=pf.thumbnail_url,
                        caption=pf.caption,
                        description=pf.description,
                        sort_order=pf.sort_order,
                        file_size_bytes=pf.file_size_bytes,
                        original_filename=pf.original_filename,
                    )
                    db.add(file)
                    await db.flush()
                existing_by_id[file.id] = file

            if file is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File id {meta.id} not found for this event",
                )

            file.file_type = meta.file_type
            file.caption = meta.caption
            file.description = meta.description
            file.original_filename = meta.original_filename
            file.sort_order = order
            if meta.thumbnail_blob_path is not None:
                file.thumbnail_url = meta.thumbnail_blob_path
            if meta.file_size_bytes is not None:
                file.file_size_bytes = meta.file_size_bytes

            if file.id not in seen:
                desired_ids.append(file.id)
                seen.add(file.id)
        else:
            file = EventMediaItem(
                event_id=event.id,
                file_type=meta.file_type,
                file_url=meta.blob_path or "",
                thumbnail_url=meta.thumbnail_blob_path,
                caption=meta.caption,
                description=meta.description,
                sort_order=order,
                file_size_bytes=meta.file_size_bytes or 0,
                original_filename=meta.original_filename,
            )
            db.add(file)
            await db.flush()
            desired_ids.append(file.id)
            seen.add(file.id)
            existing_by_id[file.id] = file
            new_file_metas.append(meta)

    # Validate limits on the final set
    final_files = [existing_by_id[fid] for fid in desired_ids]
    _validate_event_media_limits(final_files, new_file_metas)

    # Remove files not present in payload
    removed = [f for f in existing_files if f.id not in seen]

    if event.status == EventStatus.DRAFT and removed:
        storage = get_storage()
        for f in removed:
            # Don't delete blobs shared with parent event
            if f.file_url and f.file_url not in parent_blob_paths:
                await storage.delete(f.file_url)
            if f.thumbnail_url and f.thumbnail_url not in parent_blob_paths:
                await storage.delete(f.thumbnail_url)
            await db.delete(f)
        logger.debug("Removed %d files from draft event %s", len(removed), event.id)

    event.staging_file_ids = desired_ids
    logger.debug("Synced %d media items for event %s", len(desired_ids), event.id)


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
