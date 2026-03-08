"""Shared fixtures for API tests. Skips auth by overriding get_current_user."""

import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory, engine
from app.main import app
from app.models.events.user import User
from app.utils.security import get_current_user


TEST_USER_EMAIL = "test-pytest@event-flow.example.com"


def _ensure_test_user() -> User:
    """Synchronously create or fetch test user (for use with TestClient)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:

        async def _create() -> User:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(User).where(User.email == TEST_USER_EMAIL)
                )
                user = result.scalar_one_or_none()
                if user is None:
                    user = User(
                        email=TEST_USER_EMAIL,
                        password_hash="$2b$12$dummy",
                        full_name="Test User",
                        policy_hub_admin=True,
                        knowledge_hub_admin=True,
                        is_admin=True,
                    )
                    session.add(user)
                    await session.commit()
                    await session.refresh(user)
                return user

        result = loop.run_until_complete(_create())
        # Dispose pool so TestClient gets fresh connections in its own loop
        loop.run_until_complete(engine.dispose())
        return result
    finally:
        loop.close()


_test_user_cached: User | None = None


@pytest.fixture(scope="session")
def test_user() -> User:
    """Create or get the test user once per session."""
    global _test_user_cached
    if _test_user_cached is None:
        _test_user_cached = _ensure_test_user()
    return _test_user_cached


@pytest.fixture
def client(test_user: User) -> TestClient:
    """HTTP client with auth bypass (sync TestClient)."""
    async def override_get_current_user() -> User:
        return test_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app=app, base_url="http://test") as c:
        yield c

    app.dependency_overrides.pop(get_current_user, None)
    # Reset engine pool so next test gets fresh connections (avoids closed-loop issues)
    _loop = asyncio.new_event_loop()
    _loop.run_until_complete(engine.dispose())
    _loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a DB session for async test setup (if needed)."""
    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def async_client(test_user: User) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client with auth bypass."""
    async def override_get_current_user() -> User:
        return test_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.pop(get_current_user, None)
