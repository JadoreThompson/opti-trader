import httpx
import pytest
import pytest_asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from unittest.mock import MagicMock

from server.utils.db import depends_db_session
from src.server.app import app
from tests.config import smaker_async
from tests.utils import async_db_session_context


async def override_depends_db_session():
    print("nigger")
    async with smaker_async.begin() as sess:
        print("nigger nigger", sess.bind.url)
        yield sess


app.dependency_overrides[depends_db_session] = override_depends_db_session


@pytest.fixture
def patched_depends_db_session(monkeypatch):
    monkeypatch.setattr("src.utils.db.smaker_async", smaker_async)
    monkeypatch.setattr(
        "src.utils.db.get_db_session", async_db_session_context
    )
    monkeypatch.setattr("src.server.utils.db.smaker_async", smaker_async)
    monkeypatch.setattr(
        "src.server.utils.db.depends_db_session", override_depends_db_session
    )
    monkeypatch.setattr(
        "src.server.utils.auth.get_db_session", async_db_session_context
    )


@pytest_asyncio.fixture
async def async_client(
    monkeypatch, tables, user_factory_db, patched_depends_db_session
):
    mock_queue = MagicMock()
    monkeypatch.setattr("src.server.routes.orders.controller.COMMAND_QUEUE", mock_queue)

    user = user_factory_db()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:80"
    ) as client:
        await client.post(
            "/auth/login", json={"username": user.username, "password": user.password}
        )
        yield client, mock_queue, user

    del app.dependency_overrides[depends_db_session]
