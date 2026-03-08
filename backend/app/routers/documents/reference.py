"""Reference data endpoints for documents with Redis caching."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_get, cache_set
from app.database import get_db
from app.models.documents.document import DocumentType, DOCUMENT_TYPE_LABELS, ROLE_DOCUMENT_TYPES
from app.models.documents.legislation import Legislation, SubLegislation
from app.models.events.user import User
from app.schemas.documents.reference import DocumentTypeOut, LegislationOut, SubLegislationOut
from app.schemas.events.comman import APIResponse
from app.schemas.events.reference import DesignationOut, DivisionOut
from app.services.documents.document_service import get_allowed_types_for_user
from app.utils.security import get_current_user

router = APIRouter()


@router.get("/document-types", response_model=APIResponse)
async def get_document_types(
    user: User = Depends(get_current_user),
):
    allowed = get_allowed_types_for_user(user)
    print(allowed,user.policy_hub_admin,user.knowledge_hub_admin,user.is_admin,user.email,'--------++++++++++++++++')
    data = [
        DocumentTypeOut(value=DOCUMENT_TYPE_LABELS[t], label=DOCUMENT_TYPE_LABELS[t])
        for t in allowed
    ]
    return APIResponse(message="Document types fetched", status_code=200, status="success", data=data)


@router.get("/legislation", response_model=APIResponse)
async def get_legislation(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
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
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cached = await cache_get("divisions")
    if cached is not None:
        data = [DivisionOut(**item) for item in cached]
        return APIResponse(message="Divisions fetched", status_code=200, status="success", data=data)

    result = await db.execute(
        select(User.division_cluster)
        .where(User.division_cluster.isnot(None), User.division_cluster != "")
        .distinct()
        .order_by(User.division_cluster)
    )
    names = [row for row in result.scalars().all() if row]
    data = [DivisionOut(id=i + 1, name=n) for i, n in enumerate(names)]
    await cache_set("divisions", [d.model_dump() for d in data])
    return APIResponse(message="Divisions fetched", status_code=200, status="success", data=data)


@router.get("/designations", response_model=APIResponse)
async def get_designations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cached = await cache_get("designations")
    if cached is not None:
        data = [DesignationOut(**item) for item in cached]
        return APIResponse(message="Designations fetched", status_code=200, status="success", data=data)

    result = await db.execute(
        select(User.designation)
        .where(User.designation.isnot(None), User.designation != "")
        .distinct()
        .order_by(User.designation)
    )
    names = [row for row in result.scalars().all() if row]
    data = [DesignationOut(id=i + 1, name=n) for i, n in enumerate(names)]
    await cache_set("designations", [d.model_dump() for d in data])
    return APIResponse(message="Designations fetched", status_code=200, status="success", data=data)
