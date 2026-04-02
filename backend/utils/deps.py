from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt as jose_jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.events.user import User as DbUser

GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    # Defaults keep existing tests working. Real auth populates these fields.
    id: str = "STAFF001"
    email: str = "admin@eventflow.com"
    username: str = "admin"
    division_cluster: str | None = "Corporate"
    designation: str | None = "Administrator"
    status: str = "active"
    is_master_admin: bool = True
    is_policy_hub_admin: bool = True
    is_knowledge_hub_admin: bool = True


def is_token_expired(token: str) -> bool:
    """
    Best-effort expiration check from JWT `exp` claim.
    If token cannot be parsed, let Microsoft Graph be the source of truth.
    """
    # Small leeway to avoid false "expired" around boundary/clock skew.
    leeway_seconds = 60

    try:
        claims = jose_jwt.get_unverified_claims(token)
    except Exception:
        return False

    exp = claims.get("exp")
    if exp is None:
        return False

    try:
        exp_dt = datetime.fromtimestamp(float(exp), tz=timezone.utc)
    except Exception:
        return False

    return exp_dt <= datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=leeway_seconds)


def _extract_bearer_token(
    credentials: HTTPAuthorizationCredentials | None,
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    token = (credentials.credentials or "").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    return token


async def get_email_from_graph(token: str) -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            GRAPH_ME_URL,
            headers={"Authorization": f"Bearer {token}"},
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    payload = resp.json() if resp.content else {}
    # Graph commonly returns `mail` and/or `userPrincipalName` depending on tenant settings.
    email = payload.get("mail") or payload.get("userPrincipalName")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email not found for current user",
        )

    return str(email).lower()


async def authenticate(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    token = _extract_bearer_token(credentials)
    if is_token_expired(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    return await get_email_from_graph(token)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    email = await authenticate(credentials)

    user_q = select(DbUser).where(func.lower(DbUser.email) == email)
    row = (await db.execute(user_q)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found in system",
        )

    status_value = (row.status or "").strip().lower() or "inactive"
    if status_value != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not active",
        )

    return CurrentUser(
        id=row.staff_id,
        email=row.email,
        username=row.username,
        division_cluster=row.division_cluster,
        designation=row.designation,
        status=status_value,
        is_master_admin=bool(row.is_master_admin),
        is_policy_hub_admin=bool(row.is_policy_hub_admin),
        is_knowledge_hub_admin=bool(row.is_knowledge_hub_admin),
    )


def is_acivte_master_admin(user: CurrentUser) -> bool:
    return user.status == "active" and user.is_master_admin and bool(user.email)


def has_active_policy_hub_admin(user: CurrentUser) -> bool:
    return user.status == "active" and user.is_policy_hub_admin and bool(user.email)


async def is_active_kh_amdin(
    email: str,
    db: AsyncSession = Depends(get_db),
) -> bool:
    email_norm = (email or "").strip().lower()
    if not email_norm:
        return False

    user_q = select(DbUser).where(func.lower(DbUser.email) == email_norm)
    row = (await db.execute(user_q)).scalar_one_or_none()
    if row is None:
        return False

    status_value = (row.status or "").strip().lower() or "inactive"
    return status_value == "active" and bool(row.is_knowledge_hub_admin)


def require_role(*roles: str):
    """
    Dependency factory that checks if the authenticated user has ANY of the given roles.

    `roles` should be column/attribute names on `CurrentUser`, e.g.:
    - "is_master_admin"
    - "is_policy_hub_admin"
    - "is_knowledge_hub_admin"
    """

    required_roles = [r for r in roles if r]
    if not required_roles:
        raise ValueError("require_role() needs at least one role name")

    async def role_checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        has_any = any(bool(getattr(user, role, False)) for role in required_roles)
        if not has_any:
            logger.warning(
                "User %s lacks required role(s): %s (has: %s)",
                user.email,
                required_roles,
                {
                    role: bool(getattr(user, role, False))
                    for role in required_roles
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: insufficient permissions",
            )
        return user

    return role_checker


# ── Role matrix (dependencies) ────────────────────────────────────────────────
# Use these directly in endpoints:
#   admin = Depends(is_active_master_admin)
#   policy_or_kh = Depends(is_active_policy_or_kh_admin)
ROLE_MATRIX = {
    "is_active_master_admin": require_role("is_master_admin"),
    "is_active_policy_hub_admin": require_role("is_policy_hub_admin"),
    "is_active_kh_admin": require_role("is_knowledge_hub_admin"),
    "is_active_policy_or_kh_admin": require_role("is_policy_hub_admin", "is_knowledge_hub_admin"),
    "is_active_master_or_policy_or_kh_admin": require_role(
        "is_master_admin",
        "is_policy_hub_admin",
        "is_knowledge_hub_admin",
    ),
}

# Export convenient names for Depends(...)
is_active_master_admin = ROLE_MATRIX["is_active_master_admin"]
is_active_policy_hub_admin = ROLE_MATRIX["is_active_policy_hub_admin"]
is_active_kh_admin = ROLE_MATRIX["is_active_kh_admin"]
is_active_policy_or_kh_admin = ROLE_MATRIX["is_active_policy_or_kh_admin"]
is_active_master_or_policy_or_kh_admin = ROLE_MATRIX["is_active_master_or_policy_or_kh_admin"]

