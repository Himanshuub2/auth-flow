from datetime import datetime

from pydantic import BaseModel, field_validator

from models.documents.bulk_applicability import BulkApplicabilityStatus
from models.documents.document import DocumentType

ALLOWED_TEMPLATE_TYPES: set[str] = {t.value for t in DocumentType} | {"EVENTS"}


class DownloadTemplateRequest(BaseModel):
    selected_types: list[str]

    @field_validator("selected_types")
    @classmethod
    def validate_types(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one type is required")
        normalized = [t.strip().upper() for t in v]
        invalid = [t for t in normalized if t not in ALLOWED_TEMPLATE_TYPES]
        if invalid:
            allowed = sorted(ALLOWED_TEMPLATE_TYPES)
            raise ValueError(
                f"Invalid type(s): {invalid}. Allowed: {allowed}"
            )
        return normalized


class BulkApplicabilityHistoryItem(BaseModel):
    id: int
    updated_by: str
    updated_on: datetime
    status: BulkApplicabilityStatus
    file_name: str
    file_sas_url: str | None = None
    error: str | None = None
    change_remarks: str | None = None

    model_config = {"from_attributes": True}


class BulkApplicabilityUploadOut(BaseModel):
    request_id: int
    message: str
