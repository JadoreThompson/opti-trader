import pytest

from uuid import uuid4
from datetime import datetime
from engine import FuturesEngine
from enums import OrderStatus, OrderType, Side
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
        "open_quantity": 0,
    }


def create_order_conditional(i: int, quantity=None) -> dict:
    order_type = OrderType.LIMIT if i % 50 == 0 else OrderType.MARKET
    is_buy = i % 2 == 0
    side = Side.BID if is_buy else Side.ASK
    base_price = 100.0
    limit_price = None

    if order_type == OrderType.LIMIT:
        x = i % 50 + 1
        limit_price = base_price - x if is_buy else base_price + x
        tp_sl_details = {
            "take_profit": limit_price + 20 if is_buy else limit_price - 20,
            "stop_loss": limit_price - 20 if is_buy else limit_price + 20,
        }
    else:
        tp_sl_details = {
            "take_profit": base_price + 20 if is_buy else base_price - 20,
            "stop_loss": base_price - 20 if is_buy else base_price + 20,
        }

    if quantity is None:
        quantity = 10

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
        "limit_price": limit_price,
        "price": None,
        "closed_at": None,
        "closed_price": None,
        "created_at": datetime.now(),
        "amount": 100,
        "open_quantity": 0,
        **tp_sl_details,
    }
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
    engine = FuturesEngine()
    orders = tuple(create_order_conditional(i) for i in range(num_orders))

    for order in orders:
        engine.place_order(order)

    yield engine, orders
