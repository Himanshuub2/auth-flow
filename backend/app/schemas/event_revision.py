from app.schemas.event import RevisionOut
from app.schemas.event_media import MediaItemOut

from pydantic import BaseModel


class RevisionDetailOut(BaseModel):
    """A full snapshot: revision details + all media items at that media version."""
    revision: RevisionOut
    media_items: list[MediaItemOut]
