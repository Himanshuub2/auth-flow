
"""
Auth helpers used by routers/services.

This project previously returned a hardcoded user for tests.
Now auth is implemented in `utils.deps` and re-exported here so existing
imports (e.g. `from utils.security import get_current_user`) keep working.
"""

from utils.deps import (  # noqa: F401
    CurrentUser,
    authenticate,
    get_current_user,
    get_email_from_graph,
    is_active_kh_amdin,
    is_acivte_master_admin,
    is_active_policy_hub_admin,
    is_active_master_or_policy_or_kh_admin,
    is_token_expired,
)

__all__ = [
    "CurrentUser",
    "authenticate",
    "get_current_user",
    "get_email_from_graph",
    "is_token_expired",
    "is_acivte_master_admin",
    "is_active_policy_hub_admin",
    "is_active_kh_amdin",
    "is_active_master_or_policy_or_kh_admin",
]
