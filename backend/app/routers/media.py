from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.event_media import MediaItemOut
from app.services import media_service
from app.utils.security import get_current_user

router = APIRouter()


@router.get("/", response_model=list[MediaItemOut])
async def get_media(
    event_id: int,
    version: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = await media_service.get_media_items(db, event_id, version)
    return [MediaItemOut.model_validate(i) for i in items]
