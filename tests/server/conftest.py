import asyncio
import pytest
import pytest_asyncio

from faker import Faker
from httpx import ASGITransport, AsyncClient

from config import REDIS_CLIENT, TEST_BASE_URL
from engine import FuturesEngine
from enums import OrderType, Side
from tests.utils import test_depends_db_session, get_db_sess_async
from server.app import app
from server.utils.db import depends_db_session


app.dependency_overrides[depends_db_session] = test_depends_db_session


@pytest.fixture
def patched_db_session(monkeypatch):
    monkeypatch.setattr("server.utils.auth.get_db_session", get_db_sess_async)


@pytest_asyncio.fixture(loop_scope="module")
async def http_client(db, patched_db_session):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=TEST_BASE_URL
    ) as client:
        yield client


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


@pytest_asyncio.fixture(loop_scope="module")
async def futures_engine(patched_log, payload_queue, payload_pusher):
    loop = asyncio.get_event_loop()
    engine = FuturesEngine(loop, payload_queue)
    task = loop.create_task(engine.run())

    try:
        yield engine
    finally:
        task.cancel()


@pytest_asyncio.fixture(loop_scope="module")
async def instrument():
    instr = "TEST-BTC-USD-FUTURES"
    await REDIS_CLIENT.set(instr, 100.0)
    return instr


@pytest_asyncio.fixture(loop_scope="module")
async def persisted_futures_order_id(http_client_authenticated, instrument):
    """Creates a new futures limit order and returns its ID."""
    limit_bid = {
        "side": Side.BID,
        "order_type": OrderType.LIMIT,
        "limit_price": 90.0,
        "quantity": 10,
        "instrument": instrument,''
        "take_profit": 110.0,
        "stop_loss": 80.0,
    }
    rsp = await http_client_authenticated.post("/order/futures", json=limit_bid)
    data = rsp.json()
    assert rsp.status_code == 201
    assert "order_id" in data
    return data["order_id"]
