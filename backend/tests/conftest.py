"""Shared fixtures for API tests. Uses hardcoded CurrentUser (no DB auth)."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session_factory, engine
from main import app
from utils.security import CurrentUser, get_current_user

_test_user = CurrentUser()


@pytest.fixture(scope="session")
def test_user() -> CurrentUser:
    return _test_user


@pytest.fixture
def client(test_user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: test_user

    with TestClient(app=app, base_url="http://test") as c:
        yield c

    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def async_client(test_user: CurrentUser) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_current_user] = lambda: test_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.pop(get_current_user, None)
