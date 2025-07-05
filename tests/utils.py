import pytest

from uuid import uuid4
from datetime import datetime
from engine import FuturesEngine
from enums import OrderStatus, OrderType, Side
from tests.mocks import MockLock, MockPusher
from typing import Generator, Tuple


def create_order_simple(
    order_id: str,
    side: Side,
    order_type: OrderType,
    instrument: str = "BTC",
    quantity: int = 10,
    limit_price: float | None = None,
    tp_price: float | None = None,
    sl_price: float | None = None,
):
    """A simplified factory for creating test orders."""
    return {
        "order_id": order_id,
        "user_id": str(uuid4()),
        "instrument": instrument,
        "side": side,
        "order_type": order_type,
        "quantity": quantity,
        "standing_quantity": quantity,
        "status": OrderStatus.PENDING,
        "limit_price": limit_price,
        "take_profit": tp_price,
        "stop_loss": sl_price,
        "filled_price": None,
        "realised_pnl": 0.0,
        "unrealised_pnl": 0.0,
        "closed_at": None,
        "created_at": datetime.now(),
    }


def create_order_conditional(i: int) -> dict:
    is_limit_order = i % 3 == 0
    order_type = OrderType.LIMIT if is_limit_order else OrderType.MARKET
    is_buy = i % 2 == 0
    side = Side.BID if is_buy else Side.ASK
    base_price, price_step, quantity = 100.0, 0.5, 10

    order = {
        "order_id": str(i),
        "user_id": str(uuid4()),
        "instrument": "HARNESS_INSTR",
        "side": side,
        "order_type": order_type,
        "quantity": quantity,
        "standing_quantity": quantity,
        "status": OrderStatus.PENDING,
        "realised_pnl": 0.0,
        "unrealised_pnl": 0.0,
        "filled_price": None,
        "limit_price": None,
        "price": None,
        "closed_at": None,
        "closed_price": None,
        "created_at": datetime.now(),
        "amount": 100,
        "take_profit": base_price + 20 if is_buy and is_limit_order else None,
        "stop_loss": base_price - 10 if is_buy and is_limit_order else None,
    }

    if order_type == OrderType.LIMIT:
        price_offset = (i // 2 * price_step) + 1
        order["limit_price"] = round(
            base_price - price_offset if is_buy else base_price + price_offset, 2
        )
    return order


@pytest.fixture
def populated_engine(
    request,
) -> Generator[Tuple[FuturesEngine, tuple[dict, ...]], None, None]:
    """
    Creates and populates a FuturesEngine with a given number of orders.
    This replaces the fixture that used the mock engine.
    """
    num_orders = request.param
    engine = FuturesEngine(MockLock(), MockPusher())
    orders = tuple(create_order_conditional(i) for i in range(num_orders))

    for order in orders:
        engine.place_order(order)

    yield engine, orders
