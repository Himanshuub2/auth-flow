import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import BaseDocuments

SCHEMA = "documents"
USERS_SCHEMA = "users"


class BulkApplicabilityStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BulkApplicabilityRequest(BaseDocuments):
    __tablename__ = "bulk_applicability_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    selected_types: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    status: Mapped[BulkApplicabilityStatus] = mapped_column(
        Enum(
            BulkApplicabilityStatus,
            name="bulk_applicability_status",
            schema=SCHEMA,
            create_constraint=True,
        ),
        default=BulkApplicabilityStatus.PENDING,
        nullable=False,
    )

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[str] = mapped_column(
        String(255),
        ForeignKey(f"{USERS_SCHEMA}.users.staff_id"),
        nullable=False,
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(255),
        ForeignKey(f"{USERS_SCHEMA}.users.staff_id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    creator: Mapped["User"] = relationship(  # noqa: F821
        "User",
        foreign_keys=[created_by],
        primaryjoin="BulkApplicabilityRequest.created_by == User.staff_id",
        lazy="joined",
    )
