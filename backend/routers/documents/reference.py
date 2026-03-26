"""Reference data endpoints for documents with Redis caching."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cache import cache_get, cache_set
from config import settings
from database import get_db
from models.documents.document import DOCUMENT_TYPE_LABELS
from models.documents.legislation import Legislation, SubLegislation
from schemas.documents.reference import (
    DesignationOut,
    DivisionOut,
    DocumentReferencesOut,
    DocumentTypeOut,
    LegislationOut,
    SubLegislationOut,
)
from schemas.events.comman import APIResponse
from services.documents.document_service import get_allowed_types_for_user
from utils.security import CurrentUser, get_current_user

router = APIRouter()
REFERENCE_CACHE_TTL = getattr(settings, "CACHE_TTL_SECONDS", 86400) * 2


@router.get("/references", response_model=APIResponse)
async def get_document_references(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    # Document types limited to what the current admin/user can manage
    allowed_types = get_allowed_types_for_user(user)
    document_types = [
        DocumentTypeOut(value=t.value, label=DOCUMENT_TYPE_LABELS[t])
        for t in allowed_types
    ]

    # Legislation (cached)
    cached_legislation = await cache_get("legislation")
    if cached_legislation is not None:
        legislation = [LegislationOut(**item) for item in cached_legislation]
    else:
        result = await db.execute(select(Legislation).order_by(Legislation.name))
        legislation_rows = list(result.scalars().all())
        legislation = [LegislationOut.model_validate(r) for r in legislation_rows]
        await cache_set("legislation", [l.model_dump() for l in legislation], ttl=REFERENCE_CACHE_TTL)

    # All sub-legislation (cached)
    cached_sub_leg = await cache_get("sub_legislation_all")
    if cached_sub_leg is not None:
        sub_legislation = [SubLegislationOut(**item) for item in cached_sub_leg]
    else:
        result = await db.execute(
            select(SubLegislation).order_by(SubLegislation.legislation_id, SubLegislation.name)
        )
        sub_leg_rows = list(result.scalars().all())
        sub_legislation = [SubLegislationOut.model_validate(r) for r in sub_leg_rows]
        await cache_set("sub_legislation_all", [s.model_dump() for s in sub_legislation], ttl=REFERENCE_CACHE_TTL)

    divisions = [
        DivisionOut(id=1, name="Corporate"),
        DivisionOut(id=2, name="Marketing & Sales"),
        DivisionOut(id=3, name="Operations"),
        DivisionOut(id=4, name="Finance"),
    ]

    designations = [
        DesignationOut(id=1, name="Administrator"),
        DesignationOut(id=2, name="DVM"),
        DesignationOut(id=3, name="Manager"),
        DesignationOut(id=4, name="Executive"),
    ]

    data = DocumentReferencesOut(
        documentTypes=document_types,
        legislation=legislation,
        subLegislation=sub_legislation,
        divisions=divisions,
        designations=designations,
    )

    return APIResponse(
        message="Document references fetched",
        status_code=200,
        status="success",
        data=data,
    )
