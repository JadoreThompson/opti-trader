from uuid import uuid4
import pytest

from engine import SpotEngine
from engine.enums import Tag
from engine.orderbook import OrderBook
from engine.orders import SpotOrder
from enums import OrderStatus, Side


@pytest.fixture
def engine():
    """Provides a clean instance of the SpotEngine for each test."""
    return SpotEngine()


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
