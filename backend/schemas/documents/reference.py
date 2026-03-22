from pydantic import BaseModel


class DocumentTypeOut(BaseModel):
    value: str
    label: str


class LegislationOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class SubLegislationOut(BaseModel):
    id: int
    legislation_id: int
    name: str

    model_config = {"from_attributes": True}


class LinkedOptionOut(BaseModel):
    id: int
    name: str


class DivisionOut(BaseModel):
    id: int
    name: str


class DesignationOut(BaseModel):
    id: int
    name: str


class DocumentReferencesOut(BaseModel):
    documentTypes: list[DocumentTypeOut]
    legislation: list[LegislationOut]
    subLegislation: list[SubLegislationOut]
    divisions: list[DivisionOut]
    designations: list[DesignationOut]
