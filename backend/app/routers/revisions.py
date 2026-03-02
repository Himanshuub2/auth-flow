from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.event import RevisionOut
from app.schemas.event_media import MediaItemOut
from app.schemas.event_revision import RevisionDetailOut
from app.services import revision_service
from app.utils.security import get_current_user

router = APIRouter()


def _rev_to_out(rev) -> RevisionOut:
    d = {c.key: getattr(rev, c.key) for c in rev.__table__.columns}
    d["version_display"] = f"{rev.media_version}.{rev.revision_number}"
    d["created_by_name"] = rev.creator.full_name
    return RevisionOut(**d)


@router.get("/", response_model=list[RevisionOut])
async def list_revisions(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    revisions = await revision_service.list_revisions(db, event_id)
    return [_rev_to_out(r) for r in revisions]


@router.get("/{media_version}/{revision_number}", response_model=RevisionDetailOut)
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
    return RevisionDetailOut(
        revision=_rev_to_out(revision),
        media_items=[MediaItemOut.model_validate(m) for m in media_items],
    )
