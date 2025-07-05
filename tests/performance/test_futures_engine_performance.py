import pytest
from engine import FuturesEngine
from tests.mocks import MockPusher, MockLock
from tests.utils import (
    create_order_conditional,
)


PERFORMANCE_TEST_SIZES = [100, 500, 1000, 2000]


@pytest.mark.parametrize("n_new", [100, 200, 500, 1000])
def test_place_order_performance(n_new, benchmark):
    """
    Measures the performance of placing a batch of 100 new orders into an
    engine that is already populated with a varying number of orders.

    This test helps to identify performance degradation as the order book grows.
    It uses `pytest-benchmark` to run the test multiple times for statistical accuracy.

    To run only this test:
    pytest -k test_place_order_performance --benchmark-only
    """
    # Warming
    new_orders_to_place = (create_order_conditional(i) for i in range(n_new))
    engine_instance = FuturesEngine(MockLock(), MockPusher())

    def place_order_batch():
        order = next(new_orders_to_place)
        engine_instance.place_order(order)

    benchmark.pedantic(
        target=place_order_batch,
        iterations=1,
        rounds=n_new,
    )
