import pytest
import gc
from engine.enums import Tag
from engine.order import Order
from engine.orderbook import OrderBook
from enums import Side


PERFORMANCE_TEST_SIZES = [100, 500, 1000, 2000, 10_000, 100_000]


@pytest.mark.parametrize("n_new", PERFORMANCE_TEST_SIZES)
def test_orderbook_append_performance(n_new: int, benchmark):
    orderbook = OrderBook()
    sides = [Side.ASK, Side.BID]
    prices = [*range(50, 100, 2)]
    orders = (
        Order(i, Tag.ENTRY, sides[i % 2], 1, prices[i % len(prices)])
        for i in range(n_new)
    )

    def target_func():
        order = next(orders)
        orderbook.append(order, order.price)

    benchmark.pedantic(target=target_func, rounds=n_new, iterations=1)


@pytest.mark.parametrize("n_new", PERFORMANCE_TEST_SIZES)
def test_orderbook_remove_performance(n_new: int, benchmark):
    orderbook = OrderBook()
    sides = [Side.ASK, Side.BID]
    prices = [*range(50, 100, 2)]

    orders = [
        Order(i, Tag.ENTRY, sides[i % 2], 1, prices[i % len(prices)])
        for i in range(n_new)
    ]
    for order in orders:
        orderbook.append(order, order.price)

    orders = (order for order in orders)

    def target_func():
        order = next(orders)
        orderbook.remove(order, order.price)

    benchmark.pedantic(target=target_func, rounds=n_new, iterations=1)


@pytest.mark.parametrize("n_new", PERFORMANCE_TEST_SIZES)
def test_orderbook_get_order_performance(n_new: int, benchmark):
    orderbook = OrderBook()
    sides = [Side.ASK, Side.BID]
    prices = [*range(50, 100, 2)]

    orders = [
        Order(i, Tag.ENTRY, sides[i % 2], 1, prices[i % len(prices)])
        for i in range(n_new)
    ]

    for order in orders:
        orderbook.append(order, order.price)

    orders = (order for order in orders)

    def target_func():
        order = next(orders)
        for _ in orderbook.get_orders(
            order.price, "bids" if order.side == Side.BID else "asks"
        ):
            break

    benchmark.pedantic(target=target_func, rounds=n_new, iterations=1)
