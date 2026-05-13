import enum
from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator

from models.documents.bulk_applicability import BulkApplicabilityStatus
from models.documents.document import DocumentType

ALLOWED_TEMPLATE_TYPES: set[str] = {t.value for t in DocumentType} | {"EVENTS"}


class TemplateMode(str, enum.Enum):
    ALL = "ALL"
    SPECIFIC = "SPECIFIC"


class DownloadTemplateRequest(BaseModel):
    """Two modes for template generation:

    - ``ALL``: include every active record of each requested type. Requires ``selected_types``.
    - ``SPECIFIC``: include only the listed ids. Requires ``document_ids`` and/or ``event_ids``.
    """

    mode: TemplateMode = TemplateMode.ALL
    selected_types: list[str] | None = None
    document_ids: list[int] | None = None
    event_ids: list[int] | None = None

    @field_validator("selected_types")
    @classmethod
    def validate_types(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        normalized = [t.strip().upper() for t in v if t and t.strip()]
        invalid = [t for t in normalized if t not in ALLOWED_TEMPLATE_TYPES]
        if invalid:
            allowed = sorted(ALLOWED_TEMPLATE_TYPES)
            raise ValueError(f"Invalid type(s): {invalid}. Allowed: {allowed}")
        return normalized

    @field_validator("document_ids", "event_ids")
    @classmethod
    def positive_ids(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return v
        if any(i is None or i <= 0 for i in v):
            raise ValueError("ids must be positive integers")
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def validate_mode_combination(self) -> "DownloadTemplateRequest":
        if self.mode == TemplateMode.ALL:
            if not self.selected_types:
                raise ValueError("selected_types is required when mode=ALL")
        else:  # SPECIFIC
            if not (self.document_ids or self.event_ids):
                raise ValueError(
                    "Provide document_ids and/or event_ids when mode=SPECIFIC"
                )
        return self


class BulkApplicabilityHistoryItem(BaseModel):
    id: int
    updated_by: str
    updated_on: datetime
    status: BulkApplicabilityStatus
    file_name: str
    file_sas_url: str | None = None
    error: str | None = None
    change_remarks: str | None = None
    organization_vertical: str = "Organization (Vertical)"

    model_config = {"from_attributes": True}
