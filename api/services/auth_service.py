from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from google.oauth2 import id_token
from google.auth.transport import requests
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.model.user import User
from api.utils.auth import jwt_auth
from api.utils.logger import logger


async def verify_google_token(token: str) -> dict:
    """Verify a Google OAuth token and return user info."""
    try:
        user_info = id_token.verify_oauth2_token(
            token,
            requests.Request(),
            settings.VITE_GOOGLE_CLIENT_ID,
        )
    except ValueError as e:
        logger.warning("Google token verification failed: {}", str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        )

    if not user_info:
        logger.warning("Empty user info from Google token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    return user_info


async def find_or_create_user(db: AsyncSession, user_info: dict) -> User:
    """Find existing user by google_id or create a new one."""
    result = await db.execute(
        select(User).where(User.google_id == user_info["sub"])
    )
    user = result.scalar_one_or_none()

    if user:
        logger.info("Existing user found: {} ({})", user.email, user.google_id)
        return user

    try:
        user = User(
            google_id=user_info["sub"],
            name=user_info["name"],
            email=user_info["email"],
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("User created: {} ({})", user.email, user.google_id)
        return user
    except Exception as e:
        logger.error("Failed to create user in DB: {}", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating user in DB",
        )


def build_login_response(user: User) -> JSONResponse:
    """Create a JSONResponse with JWT cookie for the given user."""
    jwt_payload = {
        "sub": user.google_id,
        "email": user.email,
    }
    user_data = {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "roles": user.roles,
    }

    jwt_token = jwt_auth.create_jwt(jwt_payload)
    response = JSONResponse(
        content={"message": "Login successful", "user": user_data},
        status_code=status.HTTP_200_OK,
    )
    jwt_auth.set_http_cookie(response, jwt_token)
    logger.info("Login successful for user: {}", user.email)
    return response


def serialize_user(user: User) -> dict:
    """Convert a User model to a JSON-safe dict."""
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "roles": user.roles,
    }
