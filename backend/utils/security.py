
from dataclasses import dataclass


@dataclass
class CurrentUser:
    id: int = 1
    email: str = "admin@eventflow.com"
    full_name: str = "Admin User"
    division_cluster: str = "Corporate"
    designation: str = "Administrator"
    policy_hub_admin: bool = True
    is_admin: bool = True
    knowledge_hub_admin: bool = True


def get_current_user() -> CurrentUser:
    return CurrentUser()
