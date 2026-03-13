"""Reference data: hardcoded divisions and designations (no DB User table query)."""

from fastapi import APIRouter, Depends

from schemas.events.comman import APIResponse
from schemas.events.reference import DesignationOut, DivisionOut
from utils.security import CurrentUser, get_current_user

router = APIRouter()

HARDCODED_DIVISIONS = [
    DivisionOut(id=1, name="Corporate"),
    DivisionOut(id=2, name="Marketing & Sales"),
    DivisionOut(id=3, name="Operations"),
    DivisionOut(id=4, name="Finance"),
]

HARDCODED_DESIGNATIONS = [
    DesignationOut(id=1, name="Administrator"),
    DesignationOut(id=2, name="DVM"),
    DesignationOut(id=3, name="Manager"),
    DesignationOut(id=4, name="Executive"),
]


@router.get("/divisions", response_model=APIResponse)
async def get_divisions(
    user: CurrentUser = Depends(get_current_user),
):
    return APIResponse(message="Divisions fetched", status_code=200, status="success", data=HARDCODED_DIVISIONS)


@router.get("/designations", response_model=APIResponse)
async def get_designations(
    user: CurrentUser = Depends(get_current_user),
):
    return APIResponse(message="Designations fetched", status_code=200, status="success", data=HARDCODED_DESIGNATIONS)
