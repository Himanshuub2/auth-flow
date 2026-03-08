from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# Schema-specific bases — no schema for SQLite (use prefixed table names via db_utils)
class BaseEvents(Base):
    __abstract__ = True
    __table_args__ = {} if settings.is_sqlite else {"schema": "events"}


class BaseDocuments(Base):
    __abstract__ = True
    __table_args__ = {} if settings.is_sqlite else {"schema": "documents"}


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


