from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.events.user import User
from app.schemas.events.comman import APIResponse
from app.schemas.events.event import RevisionOut, RevisionListItemOut
from app.schemas.events.event_media import MediaItemOut
from app.schemas.events.event_revision import RevisionDetailOut
from app.services.events import revision_service
from app.utils.security import get_current_user

router = APIRouter()


def _rev_to_out(rev) -> RevisionOut:
    d = {c.key: getattr(rev, c.key) for c in rev.__table__.columns}
    d["version_display"] = f"{rev.media_version}.{rev.revision_number}"
    d["created_by_name"] = rev.creator.full_name
    return RevisionOut(**d)


def _rev_list_item_from_row(row) -> RevisionListItemOut:
    """
    Convert a lightweight DB row into the slim list item schema.
    Expects the columns: id, event_id, media_version, revision_number, created_at.
    """
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
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
):
    revision, media_items = await revision_service.get_revision_snapshot(
        db, event_id, media_version, revision_number
    )
    data = RevisionDetailOut(
        revision=_rev_to_out(revision),
        media_items=[MediaItemOut.model_validate(m) for m in media_items],
    )
    return APIResponse(message="Revision fetched", status_code=200, status="success", data=data)
