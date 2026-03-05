from typing import Any

from pydantic import BaseModel

class APIResponse(BaseModel):
    """
    Standard envelope for all API responses.

    - message: short human-readable message
    - status_code: HTTP status code returned
    - status: \"success\" or \"error\"
    - data: actual payload (object, list, etc.)
    - pagination: optional pagination block when applicable
    """
    message: str
    status_code: int
    status: str
    data: Any | None = None


class APIResponsePaginated(APIResponse):
    total: int | None = None
    page: int | None = None
    page_size: int | None = None