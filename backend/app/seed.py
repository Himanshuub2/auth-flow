"""Seed script: run with `python -m app.seed` from the backend directory."""

import asyncio
import logging

from sqlalchemy import select

from app.database import async_session_factory
from app.models.events.user import User
from app.utils.security import hash_password

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEST_USER = {
    "email": "divyanshu@test.com",
    "full_name": "Divyanshu",
    "division_cluster": "Marketing & Sales",
    "designation": "DVM",
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
            user = User(
                email=TEST_USER["email"],
                full_name=TEST_USER["full_name"],
                division_cluster=TEST_USER["division_cluster"],
                designation=TEST_USER["designation"],
                policy_hub_admin=TEST_USER["policy_hub_admin"],
                knowledge_hub_admin=TEST_USER["knowledge_hub_admin"],
                is_admin=TEST_USER["is_admin"],
            )
            session.add(user)
            logger.info("Added test user: %s", TEST_USER["email"])

        await session.commit()
        logger.info("Seeding complete")


if __name__ == "__main__":
    asyncio.run(seed())
