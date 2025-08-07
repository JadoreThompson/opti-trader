import pytest

from engine import SpotEngine
from engine.typing import CancelRequest, ModifyRequest
from enums import MarketType, OrderStatus, OrderType, Side
from tests.utils import create_engine_payload


@pytest.fixture
def engine():
    """Provides a clean instance of the SpotEngine for each test."""
    return SpotEngine()


def test_place_limit_order(engine: SpotEngine):
    instrument = "instr"

    payload = create_engine_payload(OrderType.LIMIT)
    order = payload.data.order
    order["side"] = Side.BID
    order["order_type"] = OrderType.LIMIT
    order["instrument"] = instrument
    order["limit_price"] = 99.0

    engine.place_order(payload)

    assert order["status"] == OrderStatus.PENDING
    assert order["open_quantity"] == 0
    assert order["standing_quantity"] == order["quantity"]

    ob, _ = engine._instrument_manager.get(instrument)
    book_item = ob.bids[99.0]
    assert book_item.head == book_item.tail

    assert order["order_id"] in engine._order_manager._orders


def test_place_market_order(engine: SpotEngine):
    instrument = "instr"

    payload = create_engine_payload(OrderType.MARKET)
    order = payload.data.order
    order["side"] = Side.BID
    order["order_type"] = OrderType.MARKET
    order["instrument"] = instrument

    engine.place_order(payload)

    assert order["status"] == OrderStatus.PENDING
    assert order["open_quantity"] == 0
    assert order["standing_quantity"] == order["quantity"]

    ob, _ = engine._instrument_manager.get(instrument)
    assert len(ob.asks) == 0
    assert len(ob.bids) == 1

    level = ob.bids[[*ob.bid_levels][0]]
    assert len(level.tracker) == 1

    assert order["order_id"] in engine._order_manager._orders


def test_place_stop_order(engine: SpotEngine):
    instrument = "instr"

    payload = create_engine_payload(OrderType.STOP)
    order = payload.data.order
    order["side"] = Side.BID
    order["order_type"] = OrderType.STOP
    order["instrument"] = instrument
    order["stop_price"] = 100.0

    engine.place_order(payload)

    assert order["status"] == OrderStatus.PENDING
    assert order["open_quantity"] == 0
    assert order["standing_quantity"] == order["quantity"]

    ob, _ = engine._instrument_manager.get(instrument)
    assert len(ob.asks) == 0
    assert len(ob.bids) == 1

    level = ob.bids[[*ob.bid_levels][0]]
    assert len(level.tracker) == 1

    assert order["order_id"] in engine._order_manager._orders


def test_market_bid_fills_limit_ask(engine):
    """
    Scenario: A resting limit ask is fully filled by an incoming market bid.
    """

    instrument = "abc"
    _, balance_manager = engine._instrument_manager.get(instrument, MarketType.SPOT)

    ask_limit_payload = create_engine_payload(OrderType.LIMIT)
    limit_ask = ask_limit_payload.data.order
    limit_ask["side"] = Side.ASK
    limit_ask["quantity"] = 10
    limit_ask["standing_quantity"] = 10
    limit_ask["limit_price"] = 100.0
    limit_ask["instrument"] = instrument
    limit_ask["user_id"] = "jeff"

    balance_manager._user_balances[limit_ask["user_id"]] = 100

    market_buy_payload = create_engine_payload(OrderType.MARKET)
    market_bid = market_buy_payload.data.order
    market_bid["side"] = Side.BID
    market_bid["quantity"] = 10
    market_bid["standing_quantity"] = 10
    market_bid["instrument"] = instrument

    engine.place_order(ask_limit_payload)
    engine.place_order(market_buy_payload)

    assert market_bid["open_quantity"] == 10
    assert market_bid["standing_quantity"] == 0
    assert market_bid["status"] == OrderStatus.FILLED
    assert market_bid["filled_price"] == limit_ask["limit_price"]

    assert limit_ask["open_quantity"] == 10
    assert limit_ask["standing_quantity"] == 0
    assert limit_ask["status"] == OrderStatus.FILLED
    assert limit_ask["filled_price"] == limit_ask["limit_price"]
    assert limit_ask["order_id"] not in engine._order_manager._orders

    assert balance_manager.get_balance(market_bid["user_id"]) == 10
    assert balance_manager.get_balance(limit_ask["user_id"]) == 90


def test_stop_ask_fills_stop_bid(engine):
    """
    Scenario: A resting limit bid is filled by an incoming
    limit ask which is looking to be placed below the best bid.
    """

    instrument = "abc"
    _, balance_manager = engine._instrument_manager.get(instrument, MarketType.SPOT)

    bid_limit_payload = create_engine_payload(OrderType.LIMIT)
    limit_bid = bid_limit_payload.data.order
    limit_bid["side"] = Side.BID
    limit_bid["quantity"] = 10
    limit_bid["standing_quantity"] = 10
    limit_bid["limit_price"] = 100.0
    limit_bid["instrument"] = instrument
    limit_bid["user_id"] = "bid"

    ask_limit_payload = create_engine_payload(OrderType.LIMIT)
    limit_ask = ask_limit_payload.data.order
    limit_ask["side"] = Side.ASK
    limit_ask["quantity"] = 10
    limit_ask["standing_quantity"] = 10
    limit_ask["limit_price"] = 90.0
    limit_ask["instrument"] = instrument
    limit_ask["user_id"] = "ask"

    balance_manager._user_balances[limit_ask["user_id"]] = 100

    engine.place_order(bid_limit_payload)
    engine.place_order(ask_limit_payload)

    assert limit_bid["open_quantity"] == 10
    assert limit_bid["standing_quantity"] == 0
    assert limit_bid["status"] == OrderStatus.FILLED
    assert limit_bid["filled_price"] == limit_bid["limit_price"]

    assert limit_ask["open_quantity"] == 10
    assert limit_ask["standing_quantity"] == 0
    assert limit_ask["status"] == OrderStatus.FILLED
    assert limit_ask["filled_price"] == limit_bid["limit_price"]
    assert limit_ask["order_id"] not in engine._order_manager._orders

    assert balance_manager.get_balance(limit_bid["user_id"]) == 10
    assert balance_manager.get_balance(limit_ask["user_id"]) == 90


def test_stop_ask_fills_stop_bid(engine):
    """
    Scenario: A resting limit bid is filled by an incoming
    limit ask which is looking to be placed below the best bid.
    """

    instrument = "abc"
    _, balance_manager = engine._instrument_manager.get(instrument, MarketType.SPOT)

    bid_limit_payload = create_engine_payload(OrderType.LIMIT)
    limit_bid = bid_limit_payload.data.order
    limit_bid["side"] = Side.BID
    limit_bid["quantity"] = 10
    limit_bid["standing_quantity"] = 10
    limit_bid["limit_price"] = 100.0
    limit_bid["instrument"] = instrument
    limit_bid["user_id"] = "bid"

    ask_limit_payload = create_engine_payload(OrderType.LIMIT)
    limit_ask = ask_limit_payload.data.order
    limit_ask["side"] = Side.ASK
    limit_ask["quantity"] = 10
    limit_ask["standing_quantity"] = 10
    limit_ask["limit_price"] = 90.0
    limit_ask["instrument"] = instrument
    limit_ask["user_id"] = "ask"

    balance_manager._user_balances[limit_ask["user_id"]] = 100

    engine.place_order(bid_limit_payload)
    engine.place_order(ask_limit_payload)

    assert limit_bid["open_quantity"] == 10
    assert limit_bid["standing_quantity"] == 0
    assert limit_bid["status"] == OrderStatus.FILLED
    assert limit_bid["filled_price"] == limit_bid["limit_price"]

    assert limit_ask["open_quantity"] == 10
    assert limit_ask["standing_quantity"] == 0
    assert limit_ask["status"] == OrderStatus.FILLED
    assert limit_ask["filled_price"] == limit_bid["limit_price"]
    assert limit_ask["order_id"] not in engine._order_manager._orders

    assert balance_manager.get_balance(limit_bid["user_id"]) == 10
    assert balance_manager.get_balance(limit_ask["user_id"]) == 90


def test_limit_bid_fills_limit_ask(engine):
    """
    Scenario: A resting limit ask is filled by an incoming
    limit bid which is priced above the best ask.
    """

    instrument = "abc"
    _, balance_manager = engine._instrument_manager.get(instrument, MarketType.SPOT)

    ask_limit_payload = create_engine_payload(OrderType.LIMIT)
    limit_ask = ask_limit_payload.data.order
    limit_ask["side"] = Side.ASK
    limit_ask["quantity"] = 10
    limit_ask["standing_quantity"] = 10
    limit_ask["limit_price"] = 90.0
    limit_ask["instrument"] = instrument
    limit_ask["user_id"] = "ask"

    balance_manager._user_balances[limit_ask["user_id"]] = 100

    bid_limit_payload = create_engine_payload(OrderType.LIMIT)
    limit_bid = bid_limit_payload.data.order
    limit_bid["side"] = Side.BID
    limit_bid["quantity"] = 10
    limit_bid["standing_quantity"] = 10
    limit_bid["limit_price"] = 100.0
    limit_bid["instrument"] = instrument
    limit_bid["user_id"] = "bid"

    engine.place_order(ask_limit_payload)
    engine.place_order(bid_limit_payload)

    assert limit_bid["open_quantity"] == 10
    assert limit_bid["standing_quantity"] == 0
    assert limit_bid["status"] == OrderStatus.FILLED
    assert limit_bid["filled_price"] == limit_ask["limit_price"]

    assert limit_ask["open_quantity"] == 10
    assert limit_ask["standing_quantity"] == 0
    assert limit_ask["status"] == OrderStatus.FILLED
    assert limit_ask["filled_price"] == limit_ask["limit_price"]

    assert balance_manager.get_balance(limit_bid["user_id"]) == 10
    assert balance_manager.get_balance(limit_ask["user_id"]) == 90

    assert limit_ask["order_id"] not in engine._order_manager._orders


def test_market_bid_fills_stop_ask(engine):
    """
    Scenario: A resting sto ask is fully filled by an incoming market bid.
    """

    instrument = "abc"
    _, balance_manager = engine._instrument_manager.get(instrument, MarketType.SPOT)

    ask_stop_payload = create_engine_payload(OrderType.STOP)
    stop_ask = ask_stop_payload.data.order
    stop_ask["side"] = Side.ASK
    stop_ask["quantity"] = 10
    stop_ask["standing_quantity"] = 10
    stop_ask["stop_price"] = 100.0
    stop_ask["instrument"] = instrument
    stop_ask["user_id"] = "stop"

    balance_manager._user_balances[stop_ask["user_id"]] = 100

    market_buy_payload = create_engine_payload(OrderType.MARKET)
    market_bid = market_buy_payload.data.order
    market_bid["side"] = Side.BID
    market_bid["quantity"] = 10
    market_bid["standing_quantity"] = 10
    market_bid["instrument"] = instrument
    market_bid["user_id"] = "market"

    engine.place_order(ask_stop_payload)
    engine.place_order(market_buy_payload)

    assert market_bid["open_quantity"] == 10
    assert market_bid["standing_quantity"] == 0
    assert market_bid["status"] == OrderStatus.FILLED
    assert market_bid["filled_price"] == stop_ask["stop_price"]

    assert stop_ask["open_quantity"] == 10
    assert stop_ask["standing_quantity"] == 0
    assert stop_ask["status"] == OrderStatus.FILLED
    assert stop_ask["filled_price"] == stop_ask["stop_price"]
    assert stop_ask["order_id"] not in engine._order_manager._orders

    assert balance_manager.get_balance(market_bid["user_id"]) == 10
    assert balance_manager.get_balance(stop_ask["user_id"]) == 90


def test_stop_ask_fills_stop_bid(engine):
    """
    Scenario: A resting stop bid is filled by an incoming
    stop ask which is looking to be placed below the best bid.
    """

    instrument = "abc"
    _, balance_manager = engine._instrument_manager.get(instrument, MarketType.SPOT)

    bid_ask_payload = create_engine_payload(OrderType.STOP)
    stop_bid = bid_ask_payload.data.order
    stop_bid["side"] = Side.BID
    stop_bid["quantity"] = 10
    stop_bid["standing_quantity"] = 10
    stop_bid["stop_price"] = 90.0
    stop_bid["instrument"] = instrument
    stop_bid["user_id"] = "bid"

    ask_stop_payload = create_engine_payload(OrderType.STOP)
    stop_ask = ask_stop_payload.data.order
    stop_ask["side"] = Side.ASK
    stop_ask["quantity"] = 10
    stop_ask["standing_quantity"] = 10
    stop_ask["stop_price"] = 100.0
    stop_ask["instrument"] = instrument
    stop_ask["user_id"] = "ask"

    balance_manager._user_balances[stop_ask["user_id"]] = 100

    engine.place_order(bid_ask_payload)
    engine.place_order(ask_stop_payload)

    assert stop_bid["open_quantity"] == 10
    assert stop_bid["standing_quantity"] == 0
    assert stop_bid["status"] == OrderStatus.FILLED
    assert stop_bid["filled_price"] == stop_bid["stop_price"]

    assert stop_ask["open_quantity"] == 10
    assert stop_ask["standing_quantity"] == 0
    assert stop_ask["status"] == OrderStatus.FILLED
    assert stop_ask["filled_price"] == stop_bid["stop_price"]
    assert stop_ask["order_id"] not in engine._order_manager._orders

    assert balance_manager.get_balance(stop_bid["user_id"]) == 10
    assert balance_manager.get_balance(stop_ask["user_id"]) == 90


def test_stop_bid_fills_stop_ask(engine):
    """
    Scenario: A resting limit ask is filled by an incoming
    limit bid which is priced above the best ask.
    """

    instrument = "abc"
    _, balance_manager = engine._instrument_manager.get(instrument, MarketType.SPOT)

    ask_stop_payload = create_engine_payload(OrderType.STOP)
    stop_ask = ask_stop_payload.data.order
    stop_ask["side"] = Side.ASK
    stop_ask["quantity"] = 10
    stop_ask["standing_quantity"] = 10
    stop_ask["stop_price"] = 100.0
    stop_ask["instrument"] = instrument
    stop_ask["user_id"] = "ask"

    balance_manager._user_balances[stop_ask["user_id"]] = 100

    bid_stop_payload = create_engine_payload(OrderType.STOP)
    stop_bid = bid_stop_payload.data.order
    stop_bid["side"] = Side.BID
    stop_bid["quantity"] = 10
    stop_bid["standing_quantity"] = 10
    stop_bid["stop_price"] = 90.0
    stop_bid["instrument"] = instrument
    stop_bid["user_id"] = "bid"

    engine.place_order(ask_stop_payload)
    engine.place_order(bid_stop_payload)

    assert stop_bid["open_quantity"] == 10
    assert stop_bid["standing_quantity"] == 0
    assert stop_bid["status"] == OrderStatus.FILLED
    assert stop_bid["filled_price"] == stop_ask["stop_price"]

    assert stop_ask["open_quantity"] == 10
    assert stop_ask["standing_quantity"] == 0
    assert stop_ask["status"] == OrderStatus.FILLED
    assert stop_ask["filled_price"] == stop_ask["stop_price"]

    assert balance_manager.get_balance(stop_bid["user_id"]) == 10
    assert balance_manager.get_balance(stop_ask["user_id"]) == 90

    assert stop_ask["order_id"] not in engine._order_manager._orders


def test_limit_bid_fills_multiple_limit_asks(engine):
    """
    Scenario: An incoming limit bid is large enough to fill two resting limit asks
    at different price levels, "walking the book".
    """
    instrument = "abc"
    _, balance_manager = engine._instrument_manager.get(instrument, MarketType.SPOT)

    ask_payload_1 = create_engine_payload(OrderType.LIMIT)
    limit_ask_1 = ask_payload_1.data.order
    limit_ask_1["side"] = Side.ASK
    limit_ask_1["quantity"] = 5
    limit_ask_1["standing_quantity"] = 5
    limit_ask_1["limit_price"] = 101.0
    limit_ask_1["instrument"] = instrument
    limit_ask_1["user_id"] = "asker1"
    balance_manager._user_balances[limit_ask_1["user_id"]] = 100

    ask_payload_2 = create_engine_payload(OrderType.LIMIT)
    limit_ask_2 = ask_payload_2.data.order
    limit_ask_2["side"] = Side.ASK
    limit_ask_2["quantity"] = 5
    limit_ask_2["standing_quantity"] = 5
    limit_ask_2["limit_price"] = 102.0
    limit_ask_2["instrument"] = instrument
    limit_ask_2["user_id"] = "asker2"
    balance_manager._user_balances[limit_ask_2["user_id"]] = 100

    engine.place_order(ask_payload_1)
    engine.place_order(ask_payload_2)

    bid_payload = create_engine_payload(OrderType.LIMIT)
    limit_bid = bid_payload.data.order
    limit_bid["side"] = Side.BID
    limit_bid["quantity"] = 10
    limit_bid["standing_quantity"] = 10
    limit_bid["limit_price"] = 103.0
    limit_bid["instrument"] = instrument
    limit_bid["user_id"] = "bidder"

    engine.place_order(bid_payload)

    assert limit_ask_1["status"] == OrderStatus.FILLED
    assert limit_ask_1["open_quantity"] == 5
    assert limit_ask_1["standing_quantity"] == 0
    assert limit_ask_1["filled_price"] == 101.0

    assert limit_ask_2["status"] == OrderStatus.FILLED
    assert limit_ask_2["open_quantity"] == 5
    assert limit_ask_2["standing_quantity"] == 0
    assert limit_ask_2["filled_price"] == 102.0

    assert limit_bid["status"] == OrderStatus.FILLED
    assert limit_bid["open_quantity"] == 10
    assert limit_bid["standing_quantity"] == 0
    assert limit_bid["filled_price"] == 101.5  # (5*101 + 5*102) / 10

    ob, _ = engine._instrument_manager.get(instrument)
    assert not ob.asks
    assert not ob.bids


def test_market_bid_fills_multiple_limit_asks(engine):
    """
    Scenario: An incoming market bid is large enough to fill two resting limit asks
    at different price levels.
    """
    instrument = "abc"
    _, balance_manager = engine._instrument_manager.get(instrument, MarketType.SPOT)

    ask_payload_1 = create_engine_payload(OrderType.LIMIT)
    limit_ask_1 = ask_payload_1.data.order
    limit_ask_1["side"] = Side.ASK
    limit_ask_1["quantity"] = 8
    limit_ask_1["standing_quantity"] = 8
    limit_ask_1["limit_price"] = 100.0
    limit_ask_1["instrument"] = instrument
    limit_ask_1["user_id"] = "asker1"
    balance_manager._user_balances[limit_ask_1["user_id"]] = 100

    ask_payload_2 = create_engine_payload(OrderType.LIMIT)
    limit_ask_2 = ask_payload_2.data.order
    limit_ask_2["side"] = Side.ASK
    limit_ask_2["quantity"] = 7
    limit_ask_2["standing_quantity"] = 7
    limit_ask_2["limit_price"] = 101.0
    limit_ask_2["instrument"] = instrument
    limit_ask_2["user_id"] = "asker2"
    balance_manager._user_balances[limit_ask_2["user_id"]] = 100

    engine.place_order(ask_payload_1)
    engine.place_order(ask_payload_2)

    market_bid_payload = create_engine_payload(OrderType.MARKET)
    market_bid = market_bid_payload.data.order
    market_bid["side"] = Side.BID
    market_bid["quantity"] = 15
    market_bid["standing_quantity"] = 15
    market_bid["instrument"] = instrument
    market_bid["user_id"] = "bidder"

    engine.place_order(market_bid_payload)

    assert limit_ask_1["status"] == OrderStatus.FILLED
    assert limit_ask_1["filled_price"] == 100.0
    assert limit_ask_2["status"] == OrderStatus.FILLED
    assert limit_ask_2["filled_price"] == 101.0

    # Assertions for the incoming order
    assert market_bid["status"] == OrderStatus.FILLED
    assert market_bid["open_quantity"] == 15
    assert market_bid["standing_quantity"] == 0
    # Average price: (8*100 + 7*101) / 15 = (800 + 707) / 15 = 1507 / 15
    assert market_bid["filled_price"] == pytest.approx(100.46666667)

    ob, _ = engine._instrument_manager.get(instrument)
    assert not ob.asks


def test_stop_ask_fills_multiple_limit_bids(engine):
    """
    Scenario: An incoming stop ask fills two resting limit bids.
    Based on existing tests, stop orders rest on the book like limit orders.
    """
    instrument = "abc"
    _, balance_manager = engine._instrument_manager.get(instrument, MarketType.SPOT)

    bid_payload_1 = create_engine_payload(OrderType.LIMIT)
    limit_bid_1 = bid_payload_1.data.order
    limit_bid_1["side"] = Side.BID
    limit_bid_1["quantity"] = 10
    limit_bid_1["standing_quantity"] = 10
    limit_bid_1["limit_price"] = 99.0
    limit_bid_1["instrument"] = instrument
    limit_bid_1["user_id"] = "bidder1"

    bid_payload_2 = create_engine_payload(OrderType.LIMIT)
    limit_bid_2 = bid_payload_2.data.order
    limit_bid_2["side"] = Side.BID
    limit_bid_2["quantity"] = 10
    limit_bid_2["standing_quantity"] = 10
    limit_bid_2["limit_price"] = 98.0
    limit_bid_2["instrument"] = instrument
    limit_bid_2["user_id"] = "bidder2"

    engine.place_order(bid_payload_1)
    engine.place_order(bid_payload_2)

    ask_payload = create_engine_payload(OrderType.STOP)
    stop_ask = ask_payload.data.order
    stop_ask["side"] = Side.ASK
    stop_ask["quantity"] = 20
    stop_ask["standing_quantity"] = 20
    stop_ask["stop_price"] = 100.0
    stop_ask["instrument"] = instrument
    stop_ask["user_id"] = "asker"
    balance_manager._user_balances[stop_ask["user_id"]] = 100

    engine.place_order(ask_payload)

    assert limit_bid_1["status"] == OrderStatus.FILLED, print(limit_bid_1)
    assert limit_bid_1["filled_price"] == 99.0
    assert limit_bid_2["status"] == OrderStatus.FILLED
    assert limit_bid_2["filled_price"] == 98.0

    assert stop_ask["status"] == OrderStatus.FILLED
    assert stop_ask["open_quantity"] == 20
    assert stop_ask["standing_quantity"] == 0
    # Average price: (10*99 + 10*98) / 20 = (990 + 980) / 20 = 1970 / 20 = 98.5
    assert stop_ask["filled_price"] == 98.5

    ob, _ = engine._instrument_manager.get(instrument)
    assert not ob.bids


################## Cancels #####################
def test_cancel_market_order(engine: SpotEngine):
    payload = create_engine_payload(OrderType.MARKET)
    order = payload.data.order
    order["quantity"] = 10
    order["standing_quantity"] = 10
    order["order_type"] = OrderType.MARKET

    engine.place_order(payload)
    engine.cancel_order(CancelRequest(order_id=order["order_id"]))

    assert order["status"] == OrderStatus.CANCELLED
    assert order["standing_quantity"] == 0
    assert order["open_quantity"] == 0
    assert order["closed_at"] is not None
    assert engine._order_manager.get(order["order_id"]) is None


def test_cancel_limit_order(engine: SpotEngine):
    payload = create_engine_payload(OrderType.LIMIT)
    order = payload.data.order
    order["quantity"] = 10
    order["standing_quantity"] = 10
    order["order_type"] = OrderType.LIMIT
    order["limit_price"] = 100.0

    engine.place_order(payload)
    engine.cancel_order(CancelRequest(order_id=order["order_id"]))

    assert order["status"] == OrderStatus.CANCELLED
    assert order["standing_quantity"] == 0
    assert order["open_quantity"] == 0
    assert order["closed_at"] is not None
    assert engine._order_manager.get(order["order_id"]) is None


def test_cancel_stop_order(engine: SpotEngine):
    payload = create_engine_payload(OrderType.STOP)
    order = payload.data.order
    order["quantity"] = 10
    order["standing_quantity"] = 10
    order["order_type"] = OrderType.STOP
    order["stop_price"] = 100.0

    engine.place_order(payload)
    engine.cancel_order(CancelRequest(order_id=order["order_id"]))

    assert order["status"] == OrderStatus.CANCELLED
    assert order["standing_quantity"] == 0
    assert order["open_quantity"] == 0
    assert order["closed_at"] is not None
    assert engine._order_manager.get(order["order_id"]) is None


def test_cancel_partially_filled_market_order(engine: SpotEngine):
    """
    Scenario: An aggressive market order is partially filled, and the
    resting remainder is cancelled. This test assumes a market order
    that isn't fully filled rests on the book.
    """
    instrument = "instr"

    limit_ask_payload = create_engine_payload(OrderType.LIMIT)
    limit_ask = limit_ask_payload.data.order
    limit_ask["order_type"] = OrderType.LIMIT
    limit_ask["side"] = Side.ASK
    limit_ask["instrument"] = instrument
    limit_ask["quantity"] = 10
    limit_ask["standing_quantity"] = 10
    limit_ask["limit_price"] = 100.0

    engine.place_order(limit_ask_payload)

    market_bid_payload = create_engine_payload(OrderType.MARKET)
    market_bid = market_bid_payload.data.order
    market_bid["order_type"] = OrderType.MARKET
    market_bid["side"] = Side.BID
    market_bid["instrument"] = instrument
    market_bid["quantity"] = 20
    market_bid["standing_quantity"] = 20

    engine.place_order(market_bid_payload)

    assert limit_ask["status"] == OrderStatus.FILLED
    assert market_bid["status"] == OrderStatus.PARTIALLY_FILLED
    assert market_bid["open_quantity"] == 10
    assert market_bid["standing_quantity"] == 10
    assert market_bid["order_id"] in engine._order_manager._orders

    ob, _ = engine._instrument_manager.get(instrument)
    assert len(ob.bids) == 1

    engine.cancel_order(CancelRequest(order_id=market_bid["order_id"]))

    assert market_bid["status"] == OrderStatus.CANCELLED
    assert market_bid["standing_quantity"] == 0
    assert market_bid["open_quantity"] == 10
    assert engine._order_manager.get(market_bid["order_id"]) is None
    assert len(ob.bids) == 0


def test_cancel_partially_filled_stop_order(engine: SpotEngine):
    """
    Scenario: A resting stop order is partially filled, and then the
    remainder is cancelled.
    """
    instrument = "instr"

    stop_ask_payload = create_engine_payload(OrderType.STOP)
    stop_ask = stop_ask_payload.data.order
    stop_ask["order_type"] = OrderType.STOP
    stop_ask["side"] = Side.ASK
    stop_ask["instrument"] = instrument
    stop_ask["quantity"] = 20
    stop_ask["standing_quantity"] = 20
    stop_ask["stop_price"] = 100.0
    stop_ask["order_id"] = "stop ask"

    engine.place_order(stop_ask_payload)

    market_bid_payload = create_engine_payload(OrderType.MARKET)
    market_bid = market_bid_payload.data.order
    market_bid["order_type"] = OrderType.MARKET
    market_bid["side"] = Side.BID
    market_bid["instrument"] = instrument
    market_bid["quantity"] = 10
    market_bid["standing_quantity"] = 10
    market_bid["order_id"] = "market bid"

    engine.place_order(market_bid_payload)

    assert stop_ask["status"] == OrderStatus.PARTIALLY_FILLED
    assert stop_ask["open_quantity"] == 10
    assert stop_ask["standing_quantity"] == 10
    assert market_bid["status"] == OrderStatus.FILLED

    ob, _ = engine._instrument_manager.get(instrument)
    assert stop_ask["order_id"] in engine._order_manager._orders
    assert len(ob.asks[100.0].tracker) == 1

    engine.cancel_order(CancelRequest(order_id=stop_ask["order_id"]))

    assert stop_ask["status"] == OrderStatus.CANCELLED
    assert stop_ask["standing_quantity"] == 0
    assert stop_ask["open_quantity"] == 10
    assert engine._order_manager.get(stop_ask["order_id"]) is None
    assert 100.0 not in ob.asks


def test_modify_limit_order(engine: SpotEngine):
    limit_bid_payload = create_engine_payload(OrderType.LIMIT)
    limit_bid = limit_bid_payload.data.order
    limit_bid["order_type"] = OrderType.LIMIT
    limit_bid["side"] = Side.BID
    limit_bid["standing_quantity"] = limit_bid["quantity"] = 10
    limit_bid["limit_price"] = 100.0

    engine.place_order(limit_bid_payload)

    req = ModifyRequest(order_id=limit_bid["order_id"], limit_price=110.0)
    engine.modify_order(req)

    assert limit_bid["limit_price"] == 110.0

    order = engine._order_manager.get(limit_bid["order_id"])
    assert order is not None
    assert order.price == 110.0

    ob, _ = engine._instrument_manager.get(limit_bid["instrument"])
    assert ob.bids.get(100.0) is None


def test_modify_stop_order(engine: SpotEngine):
    stop_bid_payload = create_engine_payload(OrderType.STOP)
    stop_bid = stop_bid_payload.data.order
    stop_bid["order_type"] = OrderType.STOP
    stop_bid["side"] = Side.BID
    stop_bid["standing_quantity"] = stop_bid["quantity"] = 10
    stop_bid["stop_price"] = 100.0

    engine.place_order(stop_bid_payload)

    req = ModifyRequest(order_id=stop_bid["order_id"], stop_price=110.0)
    engine.modify_order(req)

    assert stop_bid["stop_price"] == 110.0

    order = engine._order_manager.get(stop_bid["order_id"])
    assert order is not None
    assert order.price == 110.0

    ob, _ = engine._instrument_manager.get(stop_bid["instrument"])
    assert ob.bids.get(100.0) is None
