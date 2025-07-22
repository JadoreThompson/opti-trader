import asyncio
import pytest
import pytest_asyncio

from typing import Generator
from uuid import uuid4
from config import TEST_DB_ENGINE
from db_models import Base
from engine import SpotEngine
from engine.enums import Tag
from engine.orderbook import OrderBook
from engine.orders import SpotOrder
from engine.tasks import log_event
from enums import OrderStatus, Side
from services import PayloadPusher
from tests.mocks import MockCelery, MockQueue
from tests.utils import get_db_sess, smaker_async, get_db_sess_async


@pytest.fixture
def db() -> Generator[None, None, None]:
    try:
        Base.metadata.create_all(bind=TEST_DB_ENGINE)
        yield
    finally:
        Base.metadata.drop_all(bind=TEST_DB_ENGINE)


@pytest.fixture
def db_sess(db):
    with get_db_sess() as sess:
        yield sess


@pytest_asyncio.fixture
async def db_sess_async(db):
    async with smaker_async.begin() as sess:
        yield sess


@pytest.fixture
def patched_log(monkeypatch):
    """Patches log_event in engine to be synchronous and inspectable."""
    mock_log_event = MockCelery(log_event)
    monkeypatch.setattr("engine.matching_engines.spot_engine.log_event", mock_log_event)
    monkeypatch.setattr("engine.tasks.get_db_session_sync", get_db_sess)
    yield mock_log_event


@pytest_asyncio.fixture(loop_scope="module")
async def payload_queue():
    queue = MockQueue()
    yield queue


@pytest_asyncio.fixture(loop_scope="module")
async def payload_pusher(monkeypatch, db):
    monkeypatch.setattr(
        "services.payload_pusher.payload_pusher.get_db_session", get_db_sess_async
    )
    pp = PayloadPusher()
    task = asyncio.create_task(pp.start())

    try:
        yield pp
    finally:
        task.cancel()
