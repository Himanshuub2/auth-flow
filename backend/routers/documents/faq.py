from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.events.comman import APIResponse
from services.documents import faq_service
from utils.security import CurrentUser, get_current_user

router = APIRouter()


@router.get("/", response_model=APIResponse)
async def get_faq(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    data = await faq_service.get_faq_data(db)
    return APIResponse(
        message="FAQ fetched",
        status_code=200,
        status="success",
        data=data,
    )
