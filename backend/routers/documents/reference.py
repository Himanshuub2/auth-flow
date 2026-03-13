"""Reference data endpoints for documents with Redis caching."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cache import cache_get, cache_set
from database import get_db
from models.documents.document import DocumentType, DOCUMENT_TYPE_LABELS, ROLE_DOCUMENT_TYPES
from models.documents.legislation import Legislation, SubLegislation
from schemas.documents.reference import DocumentTypeOut, LegislationOut, SubLegislationOut
from schemas.events.comman import APIResponse
from schemas.events.reference import DesignationOut, DivisionOut
from services.documents.document_service import get_allowed_types_for_user
from utils.security import CurrentUser, get_current_user

router = APIRouter()


@router.get("/document-types", response_model=APIResponse)
async def get_document_types(
    user: CurrentUser = Depends(get_current_user),
):
    allowed = get_allowed_types_for_user(user)
    data = [
        DocumentTypeOut(value=DOCUMENT_TYPE_LABELS[t], label=DOCUMENT_TYPE_LABELS[t])
        for t in allowed
    ]
    return APIResponse(message="Document types fetched", status_code=200, status="success", data=data)


@router.get("/legislation", response_model=APIResponse)
async def get_legislation(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    cached = await cache_get("legislation")
    if cached is not None:
        data = [LegislationOut(**item) for item in cached]
        return APIResponse(message="Legislation fetched", status_code=200, status="success", data=data)

    result = await db.execute(select(Legislation).order_by(Legislation.name))
    rows = list(result.scalars().all())
    data = [LegislationOut.model_validate(r) for r in rows]
    await cache_set("legislation", [d.model_dump() for d in data])
    return APIResponse(message="Legislation fetched", status_code=200, status="success", data=data)


@router.get("/sub-legislation", response_model=APIResponse)
async def get_sub_legislation(
    legislation_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    cache_key = f"sub_legislation:{legislation_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        data = [SubLegislationOut(**item) for item in cached]
        return APIResponse(message="Sub-legislation fetched", status_code=200, status="success", data=data)

    result = await db.execute(
        select(SubLegislation)
        .where(SubLegislation.legislation_id == legislation_id)
        .order_by(SubLegislation.name)
    )
    rows = list(result.scalars().all())
    data = [SubLegislationOut.model_validate(r) for r in rows]
    await cache_set(cache_key, [d.model_dump() for d in data])
    return APIResponse(message="Sub-legislation fetched", status_code=200, status="success", data=data)


@router.get("/divisions", response_model=APIResponse)
async def get_divisions(
    user: CurrentUser = Depends(get_current_user),
):
    return APIResponse(
        message="Divisions fetched", status_code=200, status="success",
        data=[
            DivisionOut(id=1, name="Corporate"),
            DivisionOut(id=2, name="Marketing & Sales"),
            DivisionOut(id=3, name="Operations"),
            DivisionOut(id=4, name="Finance"),
        ],
    )


@router.get("/designations", response_model=APIResponse)
async def get_designations(
    user: CurrentUser = Depends(get_current_user),
):
    return APIResponse(
        message="Designations fetched", status_code=200, status="success",
        data=[
            DesignationOut(id=1, name="Administrator"),
            DesignationOut(id=2, name="DVM"),
            DesignationOut(id=3, name="Manager"),
            DesignationOut(id=4, name="Executive"),
        ],
    )
