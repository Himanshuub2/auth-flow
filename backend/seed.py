"""Seed script: run with `python -m seed` from the backend directory."""

import asyncio
import logging

from sqlalchemy import select

from database import async_session_factory
from models.events.user import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEST_USER = {
    "staff_id": "STAFF001",
    "email": "admin@eventflow.com",
    "username": "admin",
    "organization_type": "Corporate",
    "division_cluster": "Corporate",
    "department": "IT",
    "designation": "Administrator",
    "status": "active",
    "is_master_admin": True,
    "is_policy_hub_admin": True,
    "is_knowledge_hub_admin": True,
}


async def seed() -> None:
    async with async_session_factory() as session:
        existing_user = (
            await session.execute(select(User).where(User.staff_id == TEST_USER["staff_id"]))
        ).scalar_one_or_none()
        if not existing_user:
            user = User(**TEST_USER)
            session.add(user)
            logger.info("Added test user: %s", TEST_USER["email"])

        await session.commit()
        logger.info("Seeding complete")


if __name__ == "__main__":
    asyncio.run(seed())
