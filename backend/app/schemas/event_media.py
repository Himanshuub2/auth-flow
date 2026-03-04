from datetime import datetime

from pydantic import BaseModel

from app.models.event_media_item import FileType


class MediaItemOut(BaseModel):
    id: int
    event_id: int
    media_versions: list[int]
    file_type: FileType
    file_url: str
    thumbnail_url: str | None
    caption: str | None
    description: str | None
    sort_order: int
    file_size_bytes: int
    original_filename: str
    created_at: datetime

    model_config = {"from_attributes": True}
