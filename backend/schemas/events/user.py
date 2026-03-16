from pydantic import BaseModel


class UserOut(BaseModel):
    id: str
    email: str
    username: str
    division_cluster: str | None
    designation: str | None
    is_master_admin: bool
    is_policy_hub_admin: bool
    is_knowledge_hub_admin: bool
