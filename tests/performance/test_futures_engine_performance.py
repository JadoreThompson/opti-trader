import copy
import pytest
from tests.utils import (
    create_order_conditional,
    # Fixture Imports
    populated_engine,
)


PERFORMANCE_TEST_SIZES = [100, 500, 1000, 2000]


@pytest.mark.parametrize("populated_engine", PERFORMANCE_TEST_SIZES, indirect=True)
@pytest.mark.parametrize("n_new", [100, 200, 500, 1000])
def test_place_order_performance(populated_engine, n_new, benchmark):
    """
    Measures the performance of placing a batch of 100 new orders into an
    engine that is already populated with a varying number of orders.

    This test helps to identify performance degradation as the order book grows.
    It uses `pytest-benchmark` to run the test multiple times for statistical accuracy.

    To run only this test:
    pytest -k test_place_order_performance --benchmark-only
    """
    # Warming
    engine, existing_orders = populated_engine
    num_existing_orders = len(existing_orders)

    new_orders_to_place = tuple(
        create_order_conditional(i)
        for i in range(num_existing_orders, num_existing_orders + n_new)
    )

    def place_order_batch(engine_instance, orders_to_add):
        for order in orders_to_add:
            engine_instance.place_order(order)

    def setup_for_benchmark_round():
        fresh_engine_instance = copy.deepcopy(engine)
        return (fresh_engine_instance, new_orders_to_place), {}

    benchmark.pedantic(
        target=place_order_batch,
        setup=setup_for_benchmark_round,
        iterations=1,
        rounds=10,
    )
