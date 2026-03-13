from typing import Any

from pydantic import BaseModel


class APIResponse(BaseModel):
    """Standard envelope: message, status_code, status, data."""
    message: str
    status_code: int
    status: str
    data: Any | None = None


class APIResponsePaginated(BaseModel):
    """Envelope for list endpoints: same as APIResponse plus total, page, page_size."""
    message: str
    status_code: int
    status: str
    data: Any | None = None
    total: int | None = None
    page: int | None = None
    page_size: int | None = None
