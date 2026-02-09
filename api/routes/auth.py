from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from api.dependencies.auth import current_user, require_role
from api.model.user import User
from api.services.auth_service import (
    verify_google_token,
    find_or_create_user,
    build_login_response,
    serialize_user,
)
from api.utils.db import get_db

router = APIRouter(prefix="/auth", tags=["auth"])
oauth_scheme = HTTPBearer()


@router.get("/login")
async def google_login(
    cred: HTTPAuthorizationCredentials = Depends(oauth_scheme),
    db=Depends(get_db),
):
    user_info = await verify_google_token(cred.credentials)
    user = await find_or_create_user(db, user_info)
    return build_login_response(user)


@router.get("/me")
async def validate_user(user=Depends(current_user)):
    return JSONResponse(
        content={"message": "User validated", "user": serialize_user(user)},
        status_code=status.HTTP_200_OK,
    )


@router.get("/protected")
async def protected_api(
    user: User = Depends(require_role("employee", "admin", "superadmin")),
):
    return JSONResponse(
        content={"message": "Protected API"},
        status_code=status.HTTP_200_OK,
    )
