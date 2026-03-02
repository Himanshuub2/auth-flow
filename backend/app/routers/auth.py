from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.user import TokenOut, UserLogin, UserOut, UserRegister
from app.services import auth_service
from app.utils.security import get_current_user
from app.models.user import User

router = APIRouter()


@router.post("/register", response_model=TokenOut, status_code=201)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    user, token = await auth_service.register_user(db, data)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut, status_code=200)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    user, token = await auth_service.login_user(db, data.email, data.password)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)
