import pytest

from engine import SpotEngine
from engine.typing import (
    CancelRequest,
    LimitModifyRequest,
    ModifyRequest,
    OCOModifyRequest,
    StopModifyRequest,
)
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

    assert order["order_id"] in engine._order_stores[OrderType.LIMIT]._orders


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

    assert order["order_id"] in engine._order_stores[OrderType.MARKET]._orders


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

    assert order["order_id"] in engine._order_stores[OrderType.STOP]._orders


def test_place_oco_order(engine: SpotEngine):
    """
    Scenario: An OCO order is placed.
    Assertion: A LIMIT and a STOP order are created and placed correctly.
    """
    instrument = "instr-oco-place"

    assert not engine._order_stores[OrderType.LIMIT]._orders
    assert not engine._order_stores[OrderType.STOP]._orders

    payload = create_engine_payload(OrderType._OCO)
    above_order, below_order = payload.data.orders

    above_order["side"] = Side.BID
    above_order["order_type"] = OrderType.STOP
    above_order["instrument"] = instrument
    above_order["quantity"] = 10
    above_order["stop_price"] = 110.0

    below_order["side"] = Side.BID
    below_order["order_type"] = OrderType.LIMIT
    below_order["instrument"] = instrument
    below_order["quantity"] = 10
    below_order["limit_price"] = 90.0

    engine.place_order(payload)

    ob, _ = engine._instrument_manager.get(instrument)
    assert 110.0 in ob.bids
    assert 90.0 in ob.bids

    store = engine._order_stores[OrderType._OCO]
    stored_orders = store._orders
    assert len(stored_orders) == 2

    assert store.get(above_order["order_id"]) is not None
    assert store.get(below_order["order_id"]) is not None


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

    balance_manager._balances[limit_ask["user_id"]] = 100

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
    assert limit_ask["order_id"] not in engine._order_stores[OrderType.LIMIT]._orders

    assert balance_manager.get_balance(market_bid) == 10
    assert balance_manager.get_balance(limit_ask) == 90


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

    balance_manager._balances[limit_ask["user_id"]] = 100

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
    assert limit_ask["order_id"] not in engine._order_stores[OrderType.LIMIT]._orders

    assert balance_manager.get_balance(limit_bid) == 10
    assert balance_manager.get_balance(limit_ask) == 90


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

    balance_manager._balances[limit_ask["user_id"]] = 100

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
    assert limit_ask["order_id"] not in engine._order_stores[OrderType.LIMIT]._orders

    assert balance_manager.get_balance(limit_bid) == 10
    assert balance_manager.get_balance(limit_ask) == 90


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

    balance_manager._balances[limit_ask["user_id"]] = 100

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

    assert balance_manager.get_balance(limit_bid) == 10
    assert balance_manager.get_balance(limit_ask) == 90

    assert limit_ask["order_id"] not in engine._order_stores[OrderType.LIMIT]._orders


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

    balance_manager._balances[stop_ask["user_id"]] = 100

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
    assert stop_ask["order_id"] not in engine._order_stores[OrderType.STOP]._orders

    assert balance_manager.get_balance(market_bid) == 10
    assert balance_manager.get_balance(stop_ask) == 90


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

    balance_manager._balances[stop_ask["user_id"]] = 100

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
    assert stop_ask["order_id"] not in engine._order_stores[OrderType.STOP]._orders

    assert balance_manager.get_balance(stop_bid) == 10
    assert balance_manager.get_balance(stop_ask) == 90


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

    balance_manager._balances[stop_ask["user_id"]] = 100

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

    assert balance_manager.get_balance(stop_bid) == 10
    assert balance_manager.get_balance(stop_ask) == 90

    assert stop_ask["order_id"] not in engine._order_stores[OrderType.STOP]._orders


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
    balance_manager._balances[limit_ask_1["user_id"]] = 100

    ask_payload_2 = create_engine_payload(OrderType.LIMIT)
    limit_ask_2 = ask_payload_2.data.order
    limit_ask_2["side"] = Side.ASK
    limit_ask_2["quantity"] = 5
    limit_ask_2["standing_quantity"] = 5
    limit_ask_2["limit_price"] = 102.0
    limit_ask_2["instrument"] = instrument
    limit_ask_2["user_id"] = "asker2"
    balance_manager._balances[limit_ask_2["user_id"]] = 100

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
    balance_manager._balances[limit_ask_1["user_id"]] = 100

    ask_payload_2 = create_engine_payload(OrderType.LIMIT)
    limit_ask_2 = ask_payload_2.data.order
    limit_ask_2["side"] = Side.ASK
    limit_ask_2["quantity"] = 7
    limit_ask_2["standing_quantity"] = 7
    limit_ask_2["limit_price"] = 101.0
    limit_ask_2["instrument"] = instrument
    limit_ask_2["user_id"] = "asker2"
    balance_manager._balances[limit_ask_2["user_id"]] = 100

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
    balance_manager._balances[stop_ask["user_id"]] = 100

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


def test_market_bid_fills_oco_order(engine: SpotEngine):
    """
    Scenario: An OCO order is placed.
    Assertion: A LIMIT and a STOP order are created and placed correctly.
    """
    instrument = "instr"

    assert not engine._order_stores[OrderType.LIMIT]._orders
    assert not engine._order_stores[OrderType.STOP]._orders

    ob, bm = engine._instrument_manager.get(instrument)
    oco_payload = create_engine_payload(OrderType._OCO)
    above_order, below_order = oco_payload.data.orders
    oco_quantity = 10

    above_order["order_id"] = "above-order"
    above_order["side"] = Side.BID
    above_order["order_type"] = OrderType.STOP
    above_order["instrument"] = instrument
    above_order["standing_quantity"] = above_order["quantity"] = oco_quantity
    above_order["stop_price"] = 110.0

    below_order["order_id"] = "below-order"
    below_order["side"] = Side.BID
    below_order["order_type"] = OrderType.LIMIT
    below_order["instrument"] = instrument
    below_order["standing_quantity"] = below_order["quantity"] = oco_quantity
    below_order["limit_price"] = 90.0

    engine.place_order(oco_payload)

    market_payload = create_engine_payload(OrderType.MARKET)
    market_order = market_payload.data.order
    market_order["order_id"] = "market-order"
    market_order["side"] = Side.ASK
    market_order["instrument"] = instrument
    market_order["order_type"] = OrderType.MARKET
    market_order["standing_quantity"] = market_order["quantity"] = 15
    market_order["price"] = 100.0
    bm.increase_balance(market_order, 15)

    engine.place_order(market_payload)

    assert market_order["status"] == OrderStatus.PARTIALLY_FILLED
    assert above_order["status"] == OrderStatus.FILLED
    assert above_order["open_quantity"] == 10
    assert above_order["standing_quantity"] == 0
    assert below_order["status"] == OrderStatus.CANCELLED
    assert below_order["standing_quantity"] == 10
    assert below_order["open_quantity"] == 0

    store = engine._order_stores[OrderType._OCO]
    assert len(store._orders) == 0
    assert len(ob.bids) == 0
    assert len(ob.asks) == 1


def test_oco_partial_then_full_fill(engine: SpotEngine):
    """
    Scenario: A market ASK order partially fills the LIMIT BID of an OCO.
              A second market ASK order triggers and fully fills the STOP BID leg.
              The state should reflect correct fill, cancelation, and open/standing qty.
    """

    instrument = "instr"
    assert not engine._order_stores[OrderType.LIMIT]._orders
    assert not engine._order_stores[OrderType.STOP]._orders

    ob, bm = engine._instrument_manager.get(instrument)
    oco_payload = create_engine_payload(OrderType._OCO)
    above_order, below_order = oco_payload.data.orders
    oco_quantity = 10

    above_order["order_id"] = "above-order"
    above_order["side"] = Side.BID
    above_order["order_type"] = OrderType.STOP
    above_order["instrument"] = instrument
    above_order["stop_price"] = 110.0
    above_order["standing_quantity"] = above_order["quantity"] = oco_quantity

    below_order["order_id"] = "below-order"
    below_order["side"] = Side.BID
    below_order["order_type"] = OrderType.LIMIT
    below_order["instrument"] = instrument
    below_order["limit_price"] = 90.0
    below_order["standing_quantity"] = below_order["quantity"] = oco_quantity

    engine.place_order(oco_payload)

    market_payload1 = create_engine_payload(OrderType.MARKET)
    market_order1 = market_payload1.data.order
    market_order1["order_id"] = "market-order-1"
    market_order1["side"] = Side.ASK
    market_order1["instrument"] = instrument
    market_order1["order_type"] = OrderType.MARKET
    market_order1["price"] = 90.0  # Matches the limit price
    market_order1["standing_quantity"] = market_order1["quantity"] = 5
    bm.increase_balance(market_order1, 5)

    engine.place_order(market_payload1)

    assert market_order1["status"] == OrderStatus.FILLED
    assert above_order["standing_quantity"] == 5
    assert above_order["open_quantity"] == 5
    assert above_order["status"] == OrderStatus.PARTIALLY_FILLED
    assert below_order["status"] == OrderStatus.PENDING

    market_payload2 = create_engine_payload(OrderType.MARKET)
    market_order2 = market_payload2.data.order
    market_order2["order_id"] = "market-order-2"
    market_order2["side"] = Side.ASK
    market_order2["instrument"] = instrument
    market_order2["order_type"] = OrderType.MARKET
    market_order2["price"] = 120.0  # Triggers the stop price of 110
    market_order2["standing_quantity"] = market_order2["quantity"] = 10
    bm.increase_balance(market_order2, 10)

    engine.place_order(market_payload2)

    assert market_order2["status"] == OrderStatus.PARTIALLY_FILLED or OrderStatus.FILLED
    assert above_order["status"] == OrderStatus.FILLED
    assert above_order["standing_quantity"] == 0
    assert above_order["open_quantity"] == 10
    assert below_order["status"] == OrderStatus.CANCELLED
    assert below_order["standing_quantity"] == 10
    assert below_order["open_quantity"] == 0


def test_oco_bid_filled_ask_cancelled(engine: SpotEngine):
    """
    Scenario: OCO with BID limit and ASK stop. Market ASK fills the BID limit fully.
              ASK leg is cancelled. State reflects correct fills and cancelation.
    """
    instrument = "instr"
    ob, bm = engine._instrument_manager.get(instrument)
    oco_payload = create_engine_payload(OrderType._OCO)
    bid_leg, ask_leg = oco_payload.data.orders
    oco_quantity = 10

    # BID LIMIT at 90
    bid_leg["order_id"] = "bid-leg"
    bid_leg["side"] = Side.BID
    bid_leg["order_type"] = OrderType.LIMIT
    bid_leg["instrument"] = instrument
    bid_leg["limit_price"] = 90.0
    bid_leg["standing_quantity"] = bid_leg["quantity"] = oco_quantity

    # ASK STOP at 110
    ask_leg["order_id"] = "ask-leg"
    ask_leg["side"] = Side.ASK
    ask_leg["order_type"] = OrderType.STOP
    ask_leg["instrument"] = instrument
    ask_leg["stop_price"] = 110.0
    ask_leg["standing_quantity"] = ask_leg["quantity"] = oco_quantity
    bm.increase_balance(ask_leg, oco_quantity * 2)
    engine.place_order(oco_payload)

    # Market ASK hits BID LIMIT at 90
    market_payload = create_engine_payload(OrderType.MARKET)
    market_order = market_payload.data.order
    market_order["order_id"] = "market-ask"
    market_order["side"] = Side.ASK
    market_order["order_type"] = OrderType.MARKET
    market_order["instrument"] = instrument
    market_order["price"] = 90.0
    market_order["standing_quantity"] = market_order["quantity"] = 10
    bm.increase_balance(market_order, 10)

    engine.place_order(market_payload)

    assert market_order["status"] == OrderStatus.FILLED
    assert bid_leg["status"] == OrderStatus.FILLED
    assert bid_leg["standing_quantity"] == 0
    assert bid_leg["open_quantity"] == 10

    assert ask_leg["status"] == OrderStatus.CANCELLED
    assert ask_leg["standing_quantity"] == 10
    assert ask_leg["open_quantity"] == 0


def test_oco_bid_ask_both_partially_filled_then_one_filled(engine: SpotEngine):
    """
    Scenario: Both BID and ASK legs of OCO reside in the book.
              Market ASK partially fills BID leg.
              Market BID partially fills ASK leg.
              Another Market BID fully fills ASK leg.
              Remaining BID leg is cancelled.
    """
    instrument = "instr"
    ob, bm = engine._instrument_manager.get(instrument)
    oco_payload = create_engine_payload(OrderType._OCO)
    bid_leg, ask_leg = oco_payload.data.orders
    oco_quantity = 10

    bid_leg["order_id"] = "bid-leg"
    bid_leg["side"] = Side.BID
    bid_leg["order_type"] = OrderType.LIMIT
    bid_leg["instrument"] = instrument
    bid_leg["limit_price"] = 90.0
    bid_leg["standing_quantity"] = bid_leg["quantity"] = oco_quantity

    ask_leg["order_id"] = "ask-leg"
    ask_leg["side"] = Side.ASK
    ask_leg["order_type"] = OrderType.STOP
    ask_leg["instrument"] = instrument
    ask_leg["stop_price"] = 100.0
    ask_leg["standing_quantity"] = ask_leg["quantity"] = oco_quantity
    bm.increase_balance(ask_leg, oco_quantity * 20)

    engine.place_order(oco_payload)

    trigger_market_bid = create_engine_payload(OrderType.MARKET)
    trigger_bid = trigger_market_bid.data.order
    trigger_bid["order_id"] = "trigger-bid"
    trigger_bid["side"] = Side.BID
    trigger_bid["order_type"] = OrderType.MARKET
    trigger_bid["instrument"] = instrument
    trigger_bid["price"] = 100.0  # Triggers STOP ASK
    trigger_bid["standing_quantity"] = trigger_bid["quantity"] = 1
    engine.place_order(trigger_market_bid)

    trigger_market_ask = create_engine_payload(OrderType.MARKET)
    trigger_ask = trigger_market_ask.data.order
    trigger_ask["order_id"] = "market-ask"
    trigger_ask["side"] = Side.ASK
    trigger_ask["order_type"] = OrderType.MARKET
    trigger_ask["instrument"] = instrument
    trigger_ask["price"] = 90.0
    trigger_ask["standing_quantity"] = trigger_ask["quantity"] = 5
    bm.increase_balance(trigger_ask, 5)
    engine.place_order(trigger_market_ask)

    assert bid_leg["status"] == OrderStatus.PARTIALLY_FILLED
    assert bid_leg["standing_quantity"] == 5
    assert ask_leg["status"] == OrderStatus.PARTIALLY_FILLED
    assert ask_leg["standing_quantity"] == 9

    final_bid = create_engine_payload(OrderType.MARKET)
    final_bid_order = final_bid.data.order
    final_bid_order["order_id"] = "final-bid"
    final_bid_order["side"] = Side.BID
    final_bid_order["order_type"] = OrderType.MARKET
    final_bid_order["instrument"] = instrument
    final_bid_order["price"] = 110.0
    final_bid_order["standing_quantity"] = final_bid_order["quantity"] = 9
    bm.increase_balance(final_bid_order, 9)
    engine.place_order(final_bid)

    assert ask_leg["status"] == OrderStatus.FILLED
    assert ask_leg["standing_quantity"] == 0
    assert ask_leg["open_quantity"] == 10

    assert bid_leg["status"] == OrderStatus.PARTIALLY_FILLED
    assert bid_leg["standing_quantity"] == 5
    assert bid_leg["open_quantity"] == 5


################## CANCELS #####################
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
    assert engine._order_stores[OrderType.MARKET].get(order["order_id"]) is None


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
    assert engine._order_stores[OrderType.LIMIT].get(order["order_id"]) is None


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
    assert engine._order_stores[OrderType.STOP].get(order["order_id"]) is None


def test_cancel_partially_filled_market_order(engine: SpotEngine):
    """
    Scenario: An aggressive market order is partially filled, and the
    resting remainder is cancelled. This test assumes a market order
    that isn't fully filled rests on the book.
    """
    instrument = "instr"
    ob, bm = engine._instrument_manager.get(instrument)

    limit_ask_payload = create_engine_payload(OrderType.LIMIT)
    limit_ask = limit_ask_payload.data.order
    limit_ask["order_type"] = OrderType.LIMIT
    limit_ask["side"] = Side.ASK
    limit_ask["instrument"] = instrument
    limit_ask["quantity"] = 10
    limit_ask["standing_quantity"] = 10
    limit_ask["limit_price"] = 100.0
    bm.increase_balance(limit_ask, 100)

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
    assert market_bid["order_id"] in engine._order_stores[OrderType.MARKET]._orders

    assert len(ob.bids) == 1

    engine.cancel_order(CancelRequest(order_id=market_bid["order_id"]))

    assert market_bid["status"] == OrderStatus.PARTIALLY_FILLED
    assert market_bid["standing_quantity"] == 0
    assert market_bid["open_quantity"] == 10
    assert engine._order_stores.get(market_bid["order_id"]) is None
    assert len(ob.bids) == 0


def test_cancel_partially_filled_stop_order(engine: SpotEngine):
    """
    Scenario: A resting stop order is partially filled, and then the
    remainder is cancelled.
    """
    instrument = "instr"
    ob, bm = engine._instrument_manager.get(instrument)

    stop_ask_payload = create_engine_payload(OrderType.STOP)
    stop_ask = stop_ask_payload.data.order
    stop_ask["order_type"] = OrderType.STOP
    stop_ask["side"] = Side.ASK
    stop_ask["instrument"] = instrument
    stop_ask["quantity"] = 20
    stop_ask["standing_quantity"] = 20
    stop_ask["stop_price"] = 100.0
    stop_ask["order_id"] = "stop ask"
    bm.increase_balance(stop_ask, 100)

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

    assert stop_ask["order_id"] in engine._order_stores[OrderType.STOP]._orders
    assert len(ob.asks[100.0].tracker) == 1

    engine.cancel_order(CancelRequest(order_id=stop_ask["order_id"]))

    assert stop_ask["status"] == OrderStatus.PARTIALLY_FILLED
    assert stop_ask["standing_quantity"] == 0
    assert stop_ask["open_quantity"] == 10
    assert engine._order_stores.get(stop_ask["order_id"]) is None
    assert 100.0 not in ob.asks


def test_cancel_oco_order(engine: SpotEngine):
    instrument = "instr-oco-place"
    ob, bm = engine._instrument_manager.get(instrument)

    assert not engine._order_stores[OrderType.LIMIT]._orders
    assert not engine._order_stores[OrderType.STOP]._orders

    payload = create_engine_payload(OrderType._OCO)
    above_order, below_order = payload.data.orders

    above_order["side"] = Side.ASK
    above_order["order_type"] = OrderType.STOP
    above_order["instrument"] = instrument
    above_order["quantity"] = 10
    above_order["stop_price"] = 110.0
    bm.increase_balance(above_order, 10)

    below_order["side"] = Side.BID
    below_order["order_type"] = OrderType.LIMIT
    below_order["instrument"] = instrument
    below_order["quantity"] = 10
    below_order["limit_price"] = 90.0

    engine.place_order(payload)

    req = CancelRequest(order_id=above_order["order_id"])
    engine.cancel_order(req)

    assert above_order["status"] == OrderStatus.CANCELLED
    assert below_order["status"] == OrderStatus.CANCELLED


def test_cancel_partially_filled_oco_order_leg(engine: SpotEngine):
    instrument = "instr-oco-place"

    ob, bm = engine._instrument_manager.get(instrument)

    assert not engine._order_stores[OrderType.LIMIT]._orders
    assert not engine._order_stores[OrderType.STOP]._orders

    payload = create_engine_payload(OrderType._OCO)
    above_order, below_order = payload.data.orders

    above_order["side"] = Side.ASK
    above_order["order_type"] = OrderType.STOP
    above_order["instrument"] = instrument
    above_order["quantity"] = 10
    above_order["stop_price"] = 110.0
    bm.increase_balance(above_order, 10)

    below_order["side"] = Side.BID
    below_order["order_type"] = OrderType.LIMIT
    below_order["instrument"] = instrument
    below_order["quantity"] = 10
    below_order["limit_price"] = 90.0

    engine.place_order(payload)

    market_bid_payload = create_engine_payload(OrderType.MARKET)
    market_bid = market_bid_payload.data.order
    market_bid["order_id"] = "market bid"
    market_bid["order_type"] = OrderType.MARKET
    market_bid["side"] = Side.BID
    market_bid["instrument"] = instrument
    market_bid["quantity"] = 5
    market_bid["standing_quantity"] = 5
    market_bid["price"] = 100.0

    engine.place_order(market_bid_payload)

    req = CancelRequest(order_id=above_order["order_id"])
    engine.cancel_order(req)

    assert above_order["status"] == OrderStatus.PARTIALLY_FILLED
    assert below_order["status"] == OrderStatus.CANCELLED


################## MODIFY #####################
def test_modify_limit_order(engine: SpotEngine):
    limit_bid_payload = create_engine_payload(OrderType.LIMIT)
    limit_bid = limit_bid_payload.data.order
    limit_bid["order_type"] = OrderType.LIMIT
    limit_bid["side"] = Side.BID
    limit_bid["standing_quantity"] = limit_bid["quantity"] = 10
    limit_bid["limit_price"] = 100.0

    engine.place_order(limit_bid_payload)

    req = ModifyRequest[LimitModifyRequest](
        order_id=limit_bid["order_id"], data=LimitModifyRequest(limit_price=110.0)
    )
    engine.modify_order(req)

    assert limit_bid["limit_price"] == 110.0

    order = engine._order_stores[OrderType.LIMIT].get(limit_bid["order_id"])
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

    req = ModifyRequest[StopModifyRequest](
        order_id=stop_bid["order_id"], data=StopModifyRequest(stop_price=110.0)
    )
    engine.modify_order(req)

    assert stop_bid["stop_price"] == 110.0

    order = engine._order_stores[OrderType.STOP].get(stop_bid["order_id"])
    assert order is not None
    assert order.price == 110.0

    ob, _ = engine._instrument_manager.get(stop_bid["instrument"])
    assert ob.bids.get(100.0) is None


def test_modify_oco_order_below_order(engine: SpotEngine):
    instrument = "instr-oco-place"

    ob, bm = engine._instrument_manager.get(instrument)

    assert not engine._order_stores[OrderType.LIMIT]._orders
    assert not engine._order_stores[OrderType.STOP]._orders

    payload = create_engine_payload(OrderType._OCO)
    above_order, below_order = payload.data.orders

    above_order["side"] = Side.ASK
    above_order["order_type"] = OrderType.STOP
    above_order["instrument"] = instrument
    above_order["quantity"] = 10
    above_order["stop_price"] = 110.0
    bm.increase_balance(above_order, 10)

    below_order["side"] = Side.BID
    below_order["order_type"] = OrderType.LIMIT
    below_order["instrument"] = instrument
    below_order["quantity"] = 10
    below_order["limit_price"] = 90.0

    engine.place_order(payload)

    req = ModifyRequest(
        order_id=above_order["order_id"], data=OCOModifyRequest(below_price=80.0)
    )
    engine.modify_order(req)

    assert below_order["limit_price"] == 80.0

    assert len(ob.bids) == 1
    assert ob.bids.get(80.0) is not None


def test_modify_oco_order_below_order(engine: SpotEngine):
    instrument = "instr-oco-place"

    ob, bm = engine._instrument_manager.get(instrument)

    assert not engine._order_stores[OrderType.LIMIT]._orders
    assert not engine._order_stores[OrderType.STOP]._orders

    limit_bid_payload = create_engine_payload(OrderType.LIMIT)
    limit_bid = limit_bid_payload.data.order
    limit_bid["instrument"] = instrument
    limit_bid["order_type"] = OrderType.LIMIT
    limit_bid["side"] = Side.BID
    limit_bid["standing_quantity"] = limit_bid["quantity"] = 10
    limit_bid["limit_price"] = 100.0

    engine.place_order(limit_bid_payload)

    oco_payload = create_engine_payload(OrderType._OCO)
    above_order, below_order = oco_payload.data.orders

    above_order["order_id"] = "above"
    above_order["side"] = Side.ASK
    above_order["order_type"] = OrderType.STOP
    above_order["instrument"] = instrument
    above_order["quantity"] = 10
    above_order["stop_price"] = 95.0
    bm.increase_balance(above_order, 10)

    below_order["order_id"] = "below"
    below_order["side"] = Side.BID
    below_order["order_type"] = OrderType.LIMIT
    below_order["instrument"] = instrument
    below_order["quantity"] = 10
    below_order["limit_price"] = 90.0

    engine.place_order(oco_payload)

    req = ModifyRequest(
        order_id=above_order["order_id"], data=OCOModifyRequest(above_price=93.0)
    )
    engine.modify_order(req)

    assert above_order["stop_price"] == 93.0

    assert len(ob.asks) == 1
    assert ob.asks.get(93.0) is not None
