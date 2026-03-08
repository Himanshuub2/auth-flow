from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import BaseDocuments
from app.db_utils import documents_table, fk_documents


class Legislation(BaseDocuments):
    __tablename__ = documents_table("legislation")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    sub_legislations: Mapped[list["SubLegislation"]] = relationship(
        back_populates="legislation", lazy="selectin",
    )


class SubLegislation(BaseDocuments):
    __tablename__ = documents_table("sub_legislation")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    legislation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(fk_documents("legislation"), ondelete="CASCADE"), nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    legislation: Mapped["Legislation"] = relationship(back_populates="sub_legislations", lazy="raise")
