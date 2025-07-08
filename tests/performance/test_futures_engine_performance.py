from random import shuffle
import pytest
from engine import FuturesEngine
from tests.mocks import MockPusher, MockLock
from tests.utils import (
    create_order_conditional,
)


PERFORMANCE_TEST_SIZES = [100, 500, 1000, 2000, 10_000, 100_000]


@pytest.mark.parametrize("n_new", PERFORMANCE_TEST_SIZES)
def test_futures_engine_place_order_performance(n_new, benchmark):
    """
    Measures the performance of placing a batch of 100 new orders into an
    engine that is already populated with a varying number of orders.

    This test helps to identify performance degradation as the order book grows.
    It uses `pytest-benchmark` to run the test multiple times for statistical accuracy.

    To run only this test:
    pytest -k test_place_order_performance --benchmark-only
    """
    # Warming
    quantities = [*range(1, 100, 5)] + ([*range(10)] * 2)
    shuffle(quantities)

    new_orders_to_place = (
        create_order_conditional(i, quantities[i % len(quantities)])
        for i in range(n_new)
    )
    engine_instance = FuturesEngine(MockLock(), MockPusher())

    def place_order_batch():
        order = next(new_orders_to_place)
        # print(order["quantity"])
        engine_instance.place_order(order)

    benchmark.pedantic(
        target=place_order_batch,
        iterations=1,
        rounds=n_new,
    )
