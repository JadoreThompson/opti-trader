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
from tests.mocks import MockCelery
from tests.utils import get_db_sess, smaker_async


@pytest.fixture()
def populated_spot_engine(request):
    order_id_factory = request.param or (lambda i: f"liquidity_{i}")
    engine = SpotEngine()
    instr = "test-ticker"
    ob = engine._orderbooks.setdefault(instr, OrderBook())
    oco_manager = engine._oco_manager
    balance_manager = engine._balance_manager

    min_price = 1.0
    max_price = ob._starting_price * 2
    total_quantity = 100_000
    q = int((total_quantity * 0.1) // (max_price - min_price))
    liq_ocos = []

    for i in range(1, int(max_price - min_price) + 1):
        payload = {
            "order_id": order_id_factory(i),
            "user_id": str(uuid4()),
            "instrument": instr,
            "status": OrderStatus.PENDING,
            "side": Side.BID,
            "quantity": q,
            "standing_quantity": 0,
            "open_quantity": q,
            "filled_price": ob._starting_price,
            "take_profit": max_price - i,
            "stop_loss": max(1, i - 1),
        }
        oco_order = oco_manager.create()
        balance_manager.append(payload)
        liq_ocos.append(oco_order)

        new_order = SpotOrder(
            payload["order_id"],
            Tag.STOP_LOSS,
            Side.ASK,
            payload["open_quantity"],
            payload["stop_loss"],
            oco_id=oco_order.id,
        )
        ob.append(new_order, new_order.price)
        oco_order.leg_b = new_order

        new_order = SpotOrder(
            payload["order_id"],
            Tag.TAKE_PROFIT,
            Side.ASK,
            payload["open_quantity"],
            payload["take_profit"],
            oco_id=oco_order.id,
        )
        ob.append(new_order, new_order.price)
        oco_order.leg_c = new_order

    return engine, instr, liq_ocos


@pytest.fixture
def db() -> Generator[None, None, None]:
    try:
        Base.metadata.create_all(bind=TEST_DB_ENGINE)
        yield
    finally:
        Base.metadata.drop_all(bind=TEST_DB_ENGINE)
        ...


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
