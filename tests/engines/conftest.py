import pytest
from typing import Generator
from engine import FuturesEngine
from tests.utils import create_order_conditional


@pytest.fixture
def populated_futures_engine(
    request,
) -> Generator[tuple[FuturesEngine, tuple[dict, ...]], None, None]:
    """
    Creates and populates a FuturesEngine with a given number of orders.
    This replaces the fixture that used the mock engine.
    """
    num_orders = request.param
    engine = FuturesEngine()
    orders = tuple(create_order_conditional(i) for i in range(num_orders))

    for order in orders:
        engine.place_order(order)

    return engine, orders
