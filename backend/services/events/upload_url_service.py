import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.events.event_media_item import EventMediaItem
from schemas.events.event import UploadUrlRequest, UploadUrlResponse
from storage import get_storage

logger = logging.getLogger(__name__)

UPLOAD_SAS_EXPIRY_MINUTES = 120


async def generate_upload_urls(
    db: AsyncSession,
    request: UploadUrlRequest,
) -> UploadUrlResponse:
    slug: str | None = None
    if request.event_id is not None:
        slug = await _get_existing_slug(db, request.event_id)
    if not slug:
        slug = uuid.uuid4().hex[:12]

    base_path = f"events/events-{slug}"
    storage = get_storage()
    base_url, sas_token = storage.get_container_upload_sas(expiry_minutes=UPLOAD_SAS_EXPIRY_MINUTES)

    return UploadUrlResponse(
        slug=slug,
        base_path=base_path,
        base_url=base_url,
        sas_token=sas_token,
    )


async def _get_existing_slug(db: AsyncSession, event_id: int) -> str | None:
    result = await db.execute(
        select(EventMediaItem.file_url)
        .where(EventMediaItem.event_id == event_id)
        .limit(1)
    )
    blob_path = result.scalar_one_or_none()
    if not blob_path:
        return None
    for part in blob_path.split("/"):
        if part.startswith("events-"):
            return part.removeprefix("events-")
    return None
