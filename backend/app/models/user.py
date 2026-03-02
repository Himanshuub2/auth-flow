from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)

    division_cluster: Mapped[str | None] = mapped_column(String(100), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(100), nullable=True)

    policy_hub_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    knowledge_hub_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
