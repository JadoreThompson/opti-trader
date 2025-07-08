import pytest
from engine import FuturesEngine
from enums import OrderStatus, OrderType, Side
from tests.mocks import MockLock, MockPusher
from tests.utils import create_order_simple


@pytest.fixture
def engine():
    """Provides a clean instance of the FuturesEngine for each test."""
    return FuturesEngine(MockLock(), MockPusher())


def test_place_limit_orders_no_match(engine: FuturesEngine):
    """
    Scenario: Two limit orders are placed far from each other and should not match.
    They should both rest on the book.
    """
    instrument = "instr"
    buy_order = create_order_simple(
        "buy1", Side.BID, OrderType.LIMIT, instrument=instrument, limit_price=99.0
    )
    sell_order = create_order_simple(
        "sell1", Side.ASK, OrderType.LIMIT, instrument=instrument, limit_price=101.0
    )

    engine.place_order(buy_order)
    engine.place_order(sell_order)

    assert buy_order["status"] == OrderStatus.PENDING
    assert sell_order["status"] == OrderStatus.PENDING

    ob = engine._order_books[instrument]
    assert ob.best_bid == 99.0
    assert ob.best_ask == 101.0
    book_item = ob.bids[99.0]
    assert book_item.head == book_item.tail
    book_item = ob.asks[101.0]
    assert book_item.head == book_item.tail


def test_market_bid_fills_limit_ask(engine: FuturesEngine):
    """
    Scenario: A resting limit sell is fully filled by an incoming market buy.
    """
    limit_sell = create_order_simple(
        "sell1",
        Side.ASK,
        OrderType.LIMIT,
        quantity=10,
        limit_price=100.0,
        tp_price=90.0,
        sl_price=110.0,
    )
    market_buy = create_order_simple("buy1", Side.BID, OrderType.MARKET, quantity=10)

    engine.place_order(limit_sell)
    engine.place_order(market_buy)

    assert market_buy["status"] == OrderStatus.FILLED
    assert market_buy["filled_price"] == 100.0

    assert limit_sell["status"] == OrderStatus.FILLED
    assert limit_sell["filled_price"] == 100.0

    # Assert Order Book State
    ob = engine._order_books[limit_sell["instrument"]]
    assert ob.best_bid == 90.0  # Sell limit TP
    book_item = ob.bids[90.0]
    assert book_item.head == book_item.tail
    book_item = ob.bids[110.0]
    assert book_item.head == book_item.tail
    assert len(ob.asks.keys()) == 1


def test_market_bid_partially_fills_limit_ask(engine: FuturesEngine):
    """
    Scenario: A large resting limit sell is only partially filled by a smaller market buy.
    """
    limit_sell = create_order_simple(
        "sell1", Side.ASK, OrderType.LIMIT, quantity=50, limit_price=100.0
    )
    market_buy = create_order_simple("buy1", Side.BID, OrderType.MARKET, quantity=20)

    engine.place_order(limit_sell)
    engine.place_order(market_buy)

    # Assert
    assert market_buy["status"] == OrderStatus.FILLED
    assert market_buy["filled_price"] == 100.0

    assert limit_sell["status"] == OrderStatus.PARTIALLY_FILLED
    assert limit_sell["standing_quantity"] == 30  # 50 - 20

    ob = engine._order_books[limit_sell["instrument"]]
    assert ob.best_ask == 100.0
    book_item = ob.asks[100.0]
    assert book_item.head == book_item.tail
    assert ob.best_bid == 100.0


def test_close_long_position_for_loss(engine: FuturesEngine):
    """
    Scenario: Establish a long position, then close it at a lower price for a profit.
    """
    instrument = "btc"
    setup_sell = create_order_simple(
        "setup_sell",
        Side.ASK,
        OrderType.LIMIT,
        instrument=instrument,
        quantity=10,
        limit_price=100.0,
    )
    long_pos_order = create_order_simple(
        "long_pos", Side.BID, OrderType.MARKET, instrument=instrument, quantity=10
    )

    engine.place_order(setup_sell)
    engine.place_order(long_pos_order)

    assert long_pos_order["status"] == OrderStatus.FILLED
    assert long_pos_order["filled_price"] == 100.0
    assert engine._position_manager.get("long_pos") is not None

    # Raising price level
    setup_ask = create_order_simple(
        "setup_ask",
        Side.ASK,
        OrderType.LIMIT,
        instrument=instrument,
        quantity=10,
        limit_price=110.0,
    )
    engine.place_order(setup_ask)
    ob = engine._order_books[instrument]
    assert ob.best_ask == 110.0

    # Exiting long
    engine.close_order({"order_id": "long_pos", "quantity": "ALL"})

    assert (
        long_pos_order["status"] == OrderStatus.FILLED
    )  # Not enough bids to take out self

    setup_long_order = create_order_simple(
        "setup_long",
        Side.BID,
        OrderType.LIMIT,
        instrument=instrument,
        quantity=10,
        limit_price=90.0,
    )
    engine.place_order(setup_long_order)

    # Exiting long
    engine.close_order({"order_id": "long_pos", "quantity": "ALL"})

    assert long_pos_order["status"] == OrderStatus.CLOSED
    assert long_pos_order["closed_price"] == 90.0
    assert long_pos_order["standing_quantity"] == 0

    expected_pnl = (90.0 - 100.0) * 10
    assert long_pos_order["realised_pnl"] == pytest.approx(expected_pnl)

    assert engine._position_manager.get("long_pos") == None


def test_close_long_position_for_profit(engine: FuturesEngine):
    """
    Scenario: Establish a long position, then close it at a higher price for a profit.
    """
    instrument = "btc"
    setup_sell = create_order_simple(
        "setup_sell",
        Side.ASK,
        OrderType.LIMIT,
        instrument=instrument,
        quantity=10,
        limit_price=100.0,
    )
    long_pos_order = create_order_simple(
        "long_pos", Side.BID, OrderType.MARKET, instrument=instrument, quantity=10
    )

    engine.place_order(setup_sell)
    engine.place_order(long_pos_order)

    assert long_pos_order["status"] == OrderStatus.FILLED
    assert long_pos_order["filled_price"] == 100.0
    assert engine._position_manager.get("long_pos") is not None

    # Raising price level
    setup_ask = create_order_simple(
        "setup_ask",
        Side.ASK,
        OrderType.LIMIT,
        instrument=instrument,
        quantity=10,
        limit_price=110.0,
    )
    engine.place_order(setup_ask)
    ob = engine._order_books[instrument]
    assert ob.best_ask == 110.0

    # Exiting long
    engine.close_order({"order_id": "long_pos", "quantity": "ALL"})

    assert (
        long_pos_order["status"] == OrderStatus.FILLED
    )  # Not enough bids to take out self

    setup_long_order = create_order_simple(
        "setup_long",
        Side.BID,
        OrderType.LIMIT,
        instrument=instrument,
        quantity=10,
        limit_price=150.0,
    )
    engine.place_order(setup_long_order)

    # Exiting long
    engine.close_order({"order_id": "long_pos", "quantity": "ALL"})

    assert long_pos_order["status"] == OrderStatus.CLOSED  # There's enough bids
    assert long_pos_order["closed_price"] == 150.0
    assert long_pos_order["standing_quantity"] == 0

    expected_pnl = (150.0 - 100.0) * 10
    assert long_pos_order["realised_pnl"] == pytest.approx(expected_pnl)

    assert engine._position_manager.get("long_pos") == None


def test_modify_pending_limit_order_price(engine: FuturesEngine):
    """
    Scenario: Modify the limit price of a PENDING order that has not been filled.
    The order should be moved to the new price level in the order book.
    """
    limit_buy = create_order_simple("buy1", Side.BID, OrderType.LIMIT, limit_price=95.0)
    engine.place_order(limit_buy)

    ob = engine._order_books[limit_buy["instrument"]]
    assert ob.best_bid == 95.0
    assert 98.0 not in ob.bids

    modify_payload = {
        "order_id": "buy1",
        "limit_price": 98.0,
        "take_profit": None,
        "stop_loss": None,
    }
    engine.modify_position(modify_payload)

    assert limit_buy["status"] == OrderStatus.PENDING
    assert limit_buy["limit_price"] == 98.0

    assert ob.best_bid == 98.0, ob.bid_levels
    assert 95.0 not in ob.bids
    assert 98.0 in ob.bids
    book_item = ob.bids[98.0]
    assert book_item.head.order.payload["order_id"] == "buy1"


def test_modify_filled_order_limit_price_raises_error(engine: FuturesEngine):
    """
    Scenario: Attempting to change the limit price of a FILLED order should
    raise a ValueError, as this is an invalid operation. This test
    validates the engine's error handling for invalid modifications.
    """
    setup_sell = create_order_simple(
        "setup_sell", Side.ASK, OrderType.LIMIT, limit_price=100.0
    )
    long_pos_order = create_order_simple("long_pos", Side.BID, OrderType.MARKET)

    engine.place_order(setup_sell)
    engine.place_order(long_pos_order)

    assert long_pos_order["status"] == OrderStatus.FILLED

    modify_payload = {
        "order_id": "long_pos",
        "limit_price": 101.0,
        "take_profit": None,
        "stop_loss": None,
    }

    with pytest.raises(ValueError):
        engine.modify_position(modify_payload)


def test_cancel_pending_limit_order(engine: FuturesEngine):
    """
    Scenario: Cancel a PENDING limit order that has not been matched.
    The order should be removed from the order book, the position removed,
    and its status updated to CANCELLED.
    """
    instrument = "BTC"
    limit_buy = create_order_simple(
        "buy1", Side.BID, OrderType.LIMIT, instrument=instrument, limit_price=95.0
    )
    engine.place_order(limit_buy)

    ob = engine._order_books[instrument]
    assert ob.best_bid == 95.0, "Order should be on the book before cancellation."
    assert (
        engine._position_manager.get("buy1") is not None
    ), "Position should exist for the pending order."

    engine.cancel_order({"order_id": "buy1"})

    assert limit_buy["status"] == OrderStatus.CANCELLED
    assert limit_buy["closed_at"] is not None

    assert len(ob.bids) == 1
    assert len(ob.asks) == 0
    book_item = ob.bids[95.0]
    assert book_item.head is None and book_item.tail is None and not book_item.tracker
    assert ob.best_bid == 95.0

    assert engine._position_manager.get("buy1") is None


def test_cancel_filled_order_raises_error(engine: FuturesEngine):
    """
    Scenario: Attempt to cancel an order that has already been FILLED.
    This action is invalid and should raise a ValueError.
    """
    setup_sell = create_order_simple(
        "setup_sell", Side.ASK, OrderType.LIMIT, limit_price=100.0
    )
    market_buy = create_order_simple("market_buy", Side.BID, OrderType.MARKET)

    engine.place_order(setup_sell)
    engine.place_order(market_buy)

    assert market_buy["status"] == OrderStatus.FILLED

    with pytest.raises(ValueError):
        engine.cancel_order({"order_id": "market_buy", "quantity": "ALL"})

    with pytest.raises(ValueError):
        engine.cancel_order({"order_id": "setup_sell", "quantity": "ALL"})


def test_cancel_partially_filled_order_raises_error(engine: FuturesEngine):
    """
    Scenario: Attempt to cancel an order that is PARTIALLY_FILLED.
    This is an invalid action and should raise a ValueError.
    """
    limit_sell = create_order_simple(
        "limit_sell", Side.ASK, OrderType.LIMIT, quantity=50, limit_price=100.0
    )
    market_buy = create_order_simple(
        "market_buy", Side.BID, OrderType.MARKET, quantity=20
    )

    engine.place_order(limit_sell)
    engine.place_order(market_buy)

    assert limit_sell["status"] == OrderStatus.PARTIALLY_FILLED
    assert market_buy["status"] == OrderStatus.FILLED

    with pytest.raises(ValueError):
        engine.cancel_order({"order_id": "market_buy", "quantity": "ALL"})
