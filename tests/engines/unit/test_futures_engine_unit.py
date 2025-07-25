import pytest
from engine import FuturesEngine
from engine.typing import CloseRequest, ModifyRequest
from enums import OrderStatus, OrderType, Side
from tests.utils import create_order_simple
from typing import Generator


@pytest.fixture
def engine():
    """Provides a clean instance of the FuturesEngine for each test."""
    return FuturesEngine()


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

    ob = engine._orderbooks[instrument]
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

    ob = engine._orderbooks[limit_sell["instrument"]]
    assert ob.best_bid == 110.0  # Sell limit TP
    book_item = ob.bids[90.0]
    assert book_item.head == book_item.tail
    book_item = ob.bids[110.0]
    assert book_item.head == book_item.tail
    assert len(ob.asks.keys()) == 0


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

    assert market_buy["status"] == OrderStatus.FILLED
    assert market_buy["filled_price"] == 100.0

    assert limit_sell["status"] == OrderStatus.PARTIALLY_FILLED
    assert limit_sell["standing_quantity"] == 30  # 50 - 20

    ob = engine._orderbooks[limit_sell["instrument"]]
    assert ob.best_ask == 100.0
    book_item = ob.asks[100.0]
    assert book_item.head == book_item.tail
    assert ob.best_bid == None


def test_close_long_position_for_loss(engine: FuturesEngine):
    """
    Scenario: Establish a long position, then close it at a lower price for a loss.
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
    assert engine._positions.get("long_pos") is not None

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
    ob = engine._orderbooks[instrument]
    assert ob.best_ask == 110.0

    # Exiting long
    engine.close_order(CloseRequest(**{"order_id": "long_pos", "quantity": "ALL"}))

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

    engine.close_order(CloseRequest(**{"order_id": "long_pos", "quantity": "ALL"}))

    assert long_pos_order["status"] == OrderStatus.CLOSED
    assert long_pos_order["closed_price"] == 90.0
    assert long_pos_order["standing_quantity"] == 0

    expected_pnl = (90.0 - 100.0) * 10
    assert long_pos_order["realised_pnl"] == pytest.approx(expected_pnl)

    assert engine._positions.get("long_pos") == None


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
    assert engine._positions.get("long_pos") is not None

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
    ob = engine._orderbooks[instrument]
    assert ob.best_ask == 110.0

    # Exiting long
    engine.close_order(CloseRequest(**{"order_id": "long_pos", "quantity": "ALL"}))

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

    engine.close_order(CloseRequest(**{"order_id": "long_pos", "quantity": "ALL"}))

    assert (
        long_pos_order["status"] == OrderStatus.FILLED
    )  # setup long was filled at 110.0
    assert long_pos_order.get("closed_price") == None
    assert long_pos_order["standing_quantity"] == 0

    assert engine._positions.get("long_pos") is not None


def test_partially_close_order(engine: FuturesEngine):
    limit_buy = create_order_simple(
        "buy1", Side.BID, OrderType.LIMIT, limit_price=100.0, quantity=10
    )
    market_sell = create_order_simple("sell1", Side.ASK, OrderType.MARKET, quantity=5)

    engine.place_order(limit_buy)
    engine.place_order(market_sell)

    assert limit_buy["status"] == OrderStatus.PARTIALLY_FILLED
    assert limit_buy["filled_price"] == 100.0
    assert limit_buy["open_quantity"] == 5
    assert limit_buy["standing_quantity"] == 5

    assert market_sell["status"] == OrderStatus.FILLED
    assert market_sell["filled_price"] == 100.0
    assert market_sell["standing_quantity"] == 0

    setup_buy = create_order_simple(
        "sell2", Side.BID, OrderType.LIMIT, limit_price=100.0, quantity=5
    )
    engine.place_order(setup_buy)

    close_request = CloseRequest(order_id="buy1", quantity=2)
    engine.close_order(close_request)

    assert limit_buy["status"] == OrderStatus.PARTIALLY_FILLED
    assert limit_buy["open_quantity"] == 3
    assert limit_buy["standing_quantity"] == 5

    assert setup_buy["status"] == OrderStatus.PARTIALLY_FILLED
    assert setup_buy["standing_quantity"] == 3


def test_modify_pending_limit_order_price(engine: FuturesEngine):
    """
    Scenario: Modify the limit price of a PENDING order that has not been filled.
    The order should be moved to the new price level in the order book.
    """
    limit_buy = create_order_simple("buy1", Side.BID, OrderType.LIMIT, limit_price=95.0)
    engine.place_order(limit_buy)

    ob = engine._orderbooks[limit_buy["instrument"]]
    assert ob.best_bid == 95.0
    assert 98.0 not in ob.bids

    modify_payload = ModifyRequest(
        **{
            "order_id": "buy1",
            "limit_price": 98.0,
            "take_profit": None,
            "stop_loss": None,
        }
    )
    engine.modify_order(modify_payload)

    assert limit_buy["status"] == OrderStatus.PENDING
    assert limit_buy["limit_price"] == 98.0

    assert ob.best_bid == 98.0, ob.bid_levels
    assert 95.0 not in ob.bids
    assert 98.0 in ob.bids
    book_item = ob.bids[98.0]
    assert book_item.head.order.id == "buy1"


def test_modify_filled_order_no_effect(engine: FuturesEngine):
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

    modify_request = ModifyRequest(
        **{
            "order_id": "long_pos",
            "limit_price": 101.0,
            "take_profit": None,
            "stop_loss": None,
        }
    )
    engine.modify_order(modify_request)
    assert long_pos_order["take_profit"] == None
    assert long_pos_order["stop_loss"] == None
    assert long_pos_order["limit_price"] == None


def test_modify_limit_price_no_effect(engine: FuturesEngine):
    """
    Scenario: Attempting to change the limit price above the market price
    should not be executed. Leaving the order's state untouched.
    """
    limit_buy = create_order_simple(
        "buy1", Side.BID, OrderType.LIMIT, limit_price=95.0, quantity=10
    )
    engine.place_order(limit_buy)

    assert limit_buy["status"] == OrderStatus.PENDING

    modify_request = ModifyRequest(
        **{
            "order_id": "buy1",
            "limit_price": 101.0,
            "take_profit": 150.0,
            "stop_loss": 20.0,
        }
    )
    engine.modify_order(modify_request)

    assert limit_buy["limit_price"] == 95.0
    assert limit_buy["status"] == OrderStatus.PENDING


def test_partially_cancel_order(engine: FuturesEngine):
    limit_buy = create_order_simple(
        "buy1", Side.BID, OrderType.LIMIT, limit_price=95.0, quantity=10
    )
    engine.place_order(limit_buy)

    engine.cancel_order(CloseRequest(order_id="buy1", quantity=5))
    assert limit_buy["status"] == OrderStatus.PENDING
    assert limit_buy["filled_price"] == None
    assert limit_buy["standing_quantity"] == 5
    assert limit_buy["open_quantity"] == 0


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

    ob = engine._orderbooks[instrument]
    assert ob.best_bid == 95.0, "Order should be on the book before cancellation."
    assert (
        engine._positions.get("buy1") is not None
    ), "Position should exist for the pending order."

    engine.cancel_order(CloseRequest(**{"order_id": "buy1", "quantity": "ALL"}))
    assert limit_buy["status"] == OrderStatus.CANCELLED
    assert limit_buy["closed_at"] is not None

    assert len(ob.bids) == 0
    assert len(ob.asks) == 0
    assert engine._positions.get("buy1") is None


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

    engine.cancel_order(CloseRequest(**{"order_id": "market_buy", "quantity": "ALL"}))
    assert market_buy["status"] == OrderStatus.FILLED
    assert market_buy["standing_quantity"] == 0
    assert market_buy["open_quantity"] == 10

    engine.cancel_order(CloseRequest(**{"order_id": "setup_sell", "quantity": "ALL"}))
    assert setup_sell["status"] == OrderStatus.FILLED
    assert setup_sell["standing_quantity"] == 0
    assert setup_sell["open_quantity"] == 10


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

    engine.cancel_order(CloseRequest(**{"order_id": "limit_sell", "quantity": "ALL"}))
    assert limit_sell["filled_price"] == 100.0


def test_partial_filled_pnl(engine: FuturesEngine):
    limit_buy = create_order_simple(
        "buy1",
        Side.BID,
        OrderType.LIMIT,
        quantity=10,
        limit_price=100.0,
        tp_price=120.0,
    )
    aggressive_sell = create_order_simple(
        "agg_sell",
        Side.ASK,
        OrderType.MARKET,
        quantity=5,
    )

    engine.place_order(limit_buy)
    engine.place_order(aggressive_sell)

    assert limit_buy["status"] == OrderStatus.PARTIALLY_FILLED

    aggressive_buy = create_order_simple(
        "agg_buy",
        Side.BID,
        OrderType.MARKET,
        quantity=5,
    )
    engine.place_order(aggressive_buy)

    assert aggressive_buy["status"] == OrderStatus.FILLED
    assert limit_buy["status"] == OrderStatus.PARTIALLY_FILLED
    assert limit_buy["open_quantity"] == 0
    assert limit_buy["standing_quantity"] == 5
    assert limit_buy["unrealised_pnl"] == 0.0
    assert limit_buy["realised_pnl"] == 100.0
    assert limit_buy["filled_price"] == 100.0
