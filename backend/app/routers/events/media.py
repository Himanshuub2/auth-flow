from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.events.user import User
from app.schemas.events.comman import APIResponse
from app.schemas.events.event_media import MediaItemOut
from app.services.events import media_service
from app.utils.security import get_current_user

router = APIRouter()


@router.get("/", response_model=APIResponse)
async def get_media(
    event_id: int,
    version: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = await media_service.get_media_items(db, event_id, version)
    effective_ver = version if version is not None else 0
    data = [
        MediaItemOut(
            id=i.id,
            event_id=i.event_id,
            media_versions=[effective_ver] if effective_ver > 0 else [0],
            file_type=i.file_type,
            file_url=i.file_url,
            thumbnail_url=i.thumbnail_url,
            caption=i.caption,
            description=i.description,
            sort_order=i.sort_order,
            file_size_bytes=i.file_size_bytes,
            original_filename=i.original_filename,
            created_at=i.created_at,
        )
        for i in items
    ]
    return APIResponse(message="Media fetched", status_code=200, status="success", data=data)
