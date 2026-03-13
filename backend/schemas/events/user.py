from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    division_cluster: str | None
    designation: str | None
    policy_hub_admin: bool
    is_admin: bool
    knowledge_hub_admin: bool
