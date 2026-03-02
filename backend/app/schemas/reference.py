from pydantic import BaseModel


class DivisionOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class DesignationOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}
