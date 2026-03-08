import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events.user import User
from app.schemas.events.user import UserRegister
from app.utils.security import hash_password, verify_password, create_access_token

logger = logging.getLogger(__name__)


async def register_user(db: AsyncSession, data: UserRegister) -> tuple[User, str]:
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=data.email,
        full_name=data.full_name,
        division_cluster=data.division_cluster,
        designation=data.designation,
        policy_hub_admin=False,
        knowledge_hub_admin=False,
        is_admin=False,
    )
    db.add(user)
    await db.flush()

    token = create_access_token(user.id)
    logger.info("User registered: id=%s email=%s", user.id, user.email)
    return user, token


async def login_user(db: AsyncSession, email: str, password: str) -> tuple[User, str]:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = create_access_token(user.id)    
    logger.info("User logged in: id=%s", user.id)
    return user, token
