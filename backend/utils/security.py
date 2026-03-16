
from dataclasses import dataclass


@dataclass
class CurrentUser:
    id: str = "STAFF001"
    email: str = "admin@eventflow.com"
    username: str = "admin"
    division_cluster: str = "Corporate"
    designation: str = "Administrator"
    is_master_admin: bool = True
    is_policy_hub_admin: bool = True
    is_knowledge_hub_admin: bool = True


def get_current_user() -> CurrentUser:
    return CurrentUser()
