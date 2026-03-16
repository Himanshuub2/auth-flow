"""Simplified auth router: no registration/login, just returns hardcoded user."""

from fastapi import APIRouter, Depends

from schemas.events.user import UserOut
from utils.security import CurrentUser, get_current_user

router = APIRouter()


@router.get("/me", response_model=UserOut)
async def me(current_user: CurrentUser = Depends(get_current_user)):
    return UserOut(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        division_cluster=current_user.division_cluster,
        designation=current_user.designation,
        is_master_admin=current_user.is_master_admin,
        is_policy_hub_admin=current_user.is_policy_hub_admin,
        is_knowledge_hub_admin=current_user.is_knowledge_hub_admin,
    )
