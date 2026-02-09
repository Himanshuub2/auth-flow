from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from api.config import settings
from api.utils.logger import logger

engine = create_async_engine(
    settings.db_url,
    future=True,
    echo=True,
)

create_async_session = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


async def get_db():
    session = create_async_session()
    try:
        yield session
        await session.commit()
    except Exception as e:
        logger.error("DB session error, rolling back: {}", str(e))
        await session.rollback()
        raise
    finally:
        await session.close()
