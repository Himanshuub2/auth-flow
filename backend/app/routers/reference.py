"""Reference data for event applicability: distinct division_cluster and designation from users table."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.reference import DesignationOut, DivisionOut
from app.utils.security import get_current_user

router = APIRouter()


@router.get("/divisions", response_model=list[DivisionOut])
async def get_divisions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(User.division_cluster)
        .where(User.division_cluster.isnot(None), User.division_cluster != "")
        .distinct()
        .order_by(User.division_cluster)
    )
    names = [row for row in result.scalars().all() if row]
    return [DivisionOut(id=i + 1, name=n) for i, n in enumerate(names)]


@router.get("/designations", response_model=list[DesignationOut])
async def get_designations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(User.designation)
        .where(User.designation.isnot(None), User.designation != "")
        .distinct()
        .order_by(User.designation)
    )
    names = [row for row in result.scalars().all() if row]
    return [DesignationOut(id=i + 1, name=n) for i, n in enumerate(names)]
