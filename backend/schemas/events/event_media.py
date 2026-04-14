from datetime import datetime

from pydantic import BaseModel

from models.events.event_media_item import FileType


class MediaItemOut(BaseModel):
    id: int 
    event_id: int 
    media_versions: list[int] = []
    file_type: FileType = FileType.IMAGE
    file_url: str
    blob_path: str | None = None
    thumbnail_url: str | None = None
    thumbnail_blob_path: str | None = None
    caption: str | None = None
    description: str | None = None
    sort_order: int
    file_size_bytes: int
    original_filename: str
    created_at: datetime

    model_config = {"from_attributes": True}
