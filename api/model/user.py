

from sqlalchemy import Integer, String,Boolean
from sqlalchemy.orm import Mapped, mapped_column
from api.model.base import Base

class User(Base):
    __tablename__ = "users"
    id:Mapped[int] = mapped_column(Integer, primary_key=True)
    google_id:Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name:Mapped[str] = mapped_column(String(255), nullable=False)
    email:Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    isEmployee:Mapped[bool] = mapped_column(Boolean, default=True)
    isAdmin:Mapped[bool] = mapped_column(Boolean, default=False)
    isSuperAdmin:Mapped[bool] = mapped_column(Boolean, default=False)

    @property
    def roles(self):
        roles = []
        if self.isAdmin:
            roles.append("admin")
        if self.isSuperAdmin:
            roles.append("superadmin")
        if self.isEmployee:
            roles.append("employee")
        return roles