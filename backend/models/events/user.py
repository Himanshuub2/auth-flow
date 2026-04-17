from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from database import BaseUsers

USERS_SCHEMA = "users"


class User(BaseUsers):
    __tablename__ = "users"

    staff_id: Mapped[str] = mapped_column(String(255), primary_key=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    organization_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organization_vertical: Mapped[str | None] = mapped_column(String(255), nullable=True)

    division_cluster: Mapped[str | None] = mapped_column(String(100), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True, server_default="active")

    is_master_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    is_policy_hub_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    is_knowledge_hub_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
