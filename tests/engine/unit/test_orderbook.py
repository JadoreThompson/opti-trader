import pytest
from src.engine.orderbook import OrderBook
from src.enums import Side


@pytest.fixture
def book():
    """Returns an OrderBook instance initialized at a price of 100."""
    return OrderBook(price=100.0)


def test_orderbook_initialization(book):
    """Test the initial state of the order book."""
    assert book.price == 100.0
    assert book.best_bid is None
    assert book.best_ask is None
    assert not book.bids
    assert not book.asks


def test_append_bid_order(book, order_factory):
    """Test appending a bid order."""
    order = order_factory(side=Side.BID, price=99.0)
    book.append(order, 99.0)
    assert book.best_bid == 99.0
    assert 99.0 in book.bids
    assert list(book.get_orders(99.0, Side.BID))[0].id == order.id


def test_append_ask_order(book, order_factory):
    """Test appending an ask order."""
    order = order_factory(side=Side.ASK, price=101.0)
    book.append(order, 101.0)
    assert book.best_ask == 101.0
    assert 101.0 in book.asks
    assert list(book.get_orders(101.0, Side.ASK))[0].id == order.id


def test_best_price_updates(book, order_factory):
    """Test that best bid/ask prices are correctly updated."""
    book.append(order_factory(side=Side.BID, price=98.0), 98.0)
    book.append(order_factory(side=Side.BID, price=99.0), 99.0)
    assert book.best_bid == 99.0

    book.append(order_factory(side=Side.ASK, price=102.0), 102.0)
    book.append(order_factory(side=Side.ASK, price=101.0), 101.0)
    assert book.best_ask == 101.0


def test_remove_order(book, order_factory):
    """Test removing an order from the book."""
    order = order_factory(side=Side.BID, price=99.0)
    book.append(order, 99.0)
    book.remove(order, 99.0)
    assert 99.0 not in book.bids
    assert book.best_bid is None


def test_remove_order_updates_best_price(book, order_factory):
    """Test that removing the best priced order updates the best price."""
    book.append(order_factory(side=Side.BID, price=98.0), 98.0)
    best_order = order_factory(side=Side.BID, price=99.0)
    book.append(best_order, 99.0)
    assert book.best_bid == 99.0

    book.remove(best_order, 99.0)
    assert book.best_bid == 98.0


def test_remove_from_empty_level(book, order_factory):
    """Test that removing an order from a non-existent level does nothing."""
    order = order_factory()
    # No exception should be raised
    book.remove(order, 100.0)


def test_get_orders_from_level(book, order_factory):
    """Test retrieving all orders from a specific price level."""
    order1 = order_factory(price=101.0, side=Side.ASK)
    order2 = order_factory(price=101.0, side=Side.ASK)
    book.append(order1, 101.0)
    book.append(order2, 101.0)

    orders = list(book.get_orders(101.0, Side.ASK))
    assert len(orders) == 2
    assert orders[0].id == order1.id
    assert orders[1].id == order2.id


def test_get_orders_from_empty_level(book):
    """Test retrieving orders from an empty or non-existent level."""
    orders = list(book.get_orders(105.0, Side.ASK))
    assert len(orders) == 0
