from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select

from api.model.user import User
from api.utils.auth import jwt_auth
from api.utils.db import get_db
from api.utils.logger import logger


async def current_user(request: Request, db=Depends(get_db)):
    """Extract and verify JWT from cookie, return the authenticated User."""
    token = request.cookies.get("auth_token")
    if not token:
        logger.warning("No auth_token cookie in request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    payload = jwt_auth.verify_jwt(token)

    result = await db.execute(
        select(User).where(User.google_id == payload["sub"])
    )
    user = result.scalar_one_or_none()
    if not user:
        logger.warning("User not found for google_id: {}", payload["sub"])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    logger.debug("Authenticated user: {}", user.email)
    return user


def require_role(*roles: str):
    """Dependency factory that checks if the authenticated user has any of the given roles."""
    async def role_checker(user: User = Depends(current_user)):
        user_roles = user.roles
        if not any(role in user_roles for role in roles):
            logger.warning(
                "User {} lacks required role(s): {} (has: {})",
                user.email, roles, user_roles,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: insufficient permissions",
            )
        return user
    return role_checker
