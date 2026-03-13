"""Seed script: run with `python -m seed` from the backend directory."""

import asyncio
import logging

from sqlalchemy import select

from database import async_session_factory
from models.events.user import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEST_USER = {
    "email": "admin@eventflow.com",
    "full_name": "Admin User",
    "division_cluster": "Corporate",
    "designation": "Administrator",
    "policy_hub_admin": True,
    "knowledge_hub_admin": True,
    "is_admin": True,
}


async def seed() -> None:
    async with async_session_factory() as session:
        existing_user = (
            await session.execute(select(User).where(User.email == TEST_USER["email"]))
        ).scalar_one_or_none()
        if not existing_user:
            user = User(**TEST_USER)
            session.add(user)
            logger.info("Added test user: %s", TEST_USER["email"])

        await session.commit()
        logger.info("Seeding complete")


if __name__ == "__main__":
    asyncio.run(seed())
