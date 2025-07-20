import pytest
import pytest_asyncio

from faker import Faker
from httpx import ASGITransport, AsyncClient

from config import TEST_BASE_URL
from tests.utils import test_depends_db_session, get_db_sess_async
from server.app import app
from server.utils.db import depends_db_session


app.dependency_overrides[depends_db_session] = test_depends_db_session


@pytest.fixture
def patched_db_session(monkeypatch):
    monkeypatch.setattr("server.utils.auth.get_db_session", get_db_sess_async)


@pytest_asyncio.fixture(loop_scope="module")
async def http_client_authenticated(db, patched_db_session):
    fkr = Faker()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=TEST_BASE_URL
    ) as client:
        await client.post(
            "/auth/register",
            json={"username": fkr.user_name(), "password": fkr.password()},
        )

        yield client
