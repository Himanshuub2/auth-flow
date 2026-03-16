from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.events.comman import APIResponse
from schemas.events.event import RevisionOut, RevisionListItemOut
from schemas.events.event_media import MediaItemOut
from schemas.events.event_revision import RevisionDetailOut
from services.events import revision_service
from utils.security import CurrentUser, get_current_user

router = APIRouter()


def _rev_to_out(rev) -> RevisionOut:
    d = {c.key: getattr(rev, c.key) for c in rev.__table__.columns}
    d["version_display"] = f"{rev.media_version}.{rev.revision_number}"
    d["created_by_name"] = rev.creator.username
    event = rev.event
    d["status"] = event.status.value
    d["updated_at"] = event.updated_at
    d["deactivate_remarks"] = event.deactivate_remarks
    return RevisionOut(**d)


def _rev_list_item_from_row(row) -> RevisionListItemOut:
    return RevisionListItemOut(
        id=row.id,
        event_id=row.event_id,
        media_version=row.media_version,
        revision_number=row.revision_number,
        version_display=f"{row.media_version}.{row.revision_number}",
        created_at=row.created_at,
    )


@router.get("/", response_model=APIResponse)
async def list_revisions(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    rows = await revision_service.list_revisions(db, event_id)
    data = [_rev_list_item_from_row(r) for r in rows]
    return APIResponse(message="Revisions fetched", status_code=200, status="success", data=data)


@router.get("/{media_version}/{revision_number}", response_model=APIResponse)
async def get_revision(
    event_id: int,
    media_version: int,
    revision_number: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    revision, media_items = await revision_service.get_revision_snapshot(
        db, event_id, media_version, revision_number
    )
    data = RevisionDetailOut(
        revision=_rev_to_out(revision),
        media_items=[
            MediaItemOut(
                id=m.id,
                event_id=m.event_id,
                media_versions=[media_version],
                file_type=m.file_type,
                file_url=m.file_url,
                thumbnail_url=m.thumbnail_url,
                caption=m.caption,
                description=m.description,
                sort_order=m.sort_order,
                file_size_bytes=m.file_size_bytes,
                original_filename=m.original_filename,
                created_at=m.created_at,
            )
            for m in media_items
        ],
    )
    return APIResponse(message="Revision fetched", status_code=200, status="success", data=data)
