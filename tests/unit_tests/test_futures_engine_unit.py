import pytest

from uuid import uuid4
from datetime import datetime
from engine import FuturesEngine
from enums import OrderStatus, OrderType, Side
from tests.mocks import MockLock, MockPusher


@pytest.fixture
def engine():
    """Provides a clean instance of the FuturesEngine for each test."""
    return FuturesEngine(MockLock(), MockPusher())


def create_order(
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


def test_place_limit_orders_no_match(engine: FuturesEngine):
    """
    Scenario: Two limit orders are placed far from each other and should not match.
    They should both rest on the book.
    """
    instrument = "instr"
    buy_order = create_order(
        "buy1", Side.BID, OrderType.LIMIT, instrument=instrument, limit_price=99.0
    )
    sell_order = create_order(
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
    limit_sell = create_order(
        "sell1",
        Side.ASK,
        OrderType.LIMIT,
        quantity=10,
        limit_price=100.0,
        tp_price=90.0,
        sl_price=110.0,
    )
    market_buy = create_order("buy1", Side.BID, OrderType.MARKET, quantity=10)

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
    limit_sell = create_order(
        "sell1", Side.ASK, OrderType.LIMIT, quantity=50, limit_price=100.0
    )
    engine.place_order(limit_sell)

    market_buy = create_order("buy1", Side.BID, OrderType.MARKET, quantity=20)
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


def test_close_long_position_for_profit(engine: FuturesEngine):
    """
    Scenario: Establish a long position, then close it at a higher price for a profit.
    """
    instrument = "btc"
    setup_sell = create_order(
        "setup_sell",
        Side.ASK,
        OrderType.LIMIT,
        instrument=instrument,
        quantity=10,
        limit_price=100.0,
    )
    long_pos_order = create_order(
        "long_pos", Side.BID, OrderType.MARKET, instrument=instrument, quantity=10
    )

    engine.place_order(setup_sell)
    engine.place_order(long_pos_order)

    assert long_pos_order["status"] == OrderStatus.FILLED
    assert long_pos_order["filled_price"] == 100.0
    assert engine._position_manager.get("long_pos") is not None

    # Raising price level
    setup_ask = create_order(
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
    engine.close_order({"order_id": "long_pos"})

    assert long_pos_order["status"] == OrderStatus.CLOSED
    assert long_pos_order["closed_price"] == 110.0
    assert long_pos_order["standing_quantity"] == 0

    expected_pnl = (110.0 - 100.0) * 10
    assert long_pos_order["realised_pnl"] == pytest.approx(expected_pnl)

    assert engine._position_manager.get("long_pos") == None
