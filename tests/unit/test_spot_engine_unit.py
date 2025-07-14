from pprint import pprint
import sys
from typing import assert_type
import pytest
from engine import SpotEngine
from engine.orderbook.orderbook import OrderBook
from engine.typing import CloseRequest, ModifyRequest
from enums import OrderStatus, OrderType, Side
from tests.utils import create_order_simple


@pytest.fixture
def engine():
    """Provides a clean instance of the SpotEngine for each test."""
    return SpotEngine()


@pytest.fixture()
def populated_engine_book():
    engine = SpotEngine()
    instr = "test-ticker"
    ob = engine._orderbooks.setdefault(instr, OrderBook())
    pos_ls = engine._populate_book(ob, instr, 1_000_000)
    return engine, instr, pos_ls


def test_place_limit_orders_no_match(engine: SpotEngine):
    """
    Scenario: Two limit orders are placed far from each other and should not match.
    They should both rest on the book.
    """
    instrument = "instr"
    buy_order = create_order_simple(
        "buy1", Side.BID, OrderType.LIMIT, instrument=instrument, limit_price=99.0
    )

    engine.place_order(buy_order)

    assert buy_order["status"] == OrderStatus.PENDING

    ob = engine._orderbooks[instrument]
    book_item = ob.bids[99.0]
    assert book_item.head == book_item.tail


def test_market_bid_gets_filled(populated_engine_book):
    """
    Scenario: A resting limit sell is fully filled by an incoming market buy.
    """
    engine, instrument, _ = populated_engine_book
    market_buy = create_order_simple(
        "buy1", Side.BID, OrderType.MARKET, quantity=10, instrument=instrument
    )

    engine.place_order(market_buy)
    assert market_buy["open_quantity"] == 10
    assert market_buy["standing_quantity"] == 0


def test_market_bid_limit_ask_neutralise(engine: SpotEngine):
    limit_sell = create_order_simple("sell1", Side.ASK, OrderType.LIMIT, quantity=10, limit_price=100.0)
    market_buy = create_order_simple("buy1", Side.BID, OrderType.MARKET, quantity=10)

    engine.place_order(limit_sell)
    engine.place_order(market_buy)

    assert market_buy["standing_quantity"] == 0
    assert market_buy["open_quantity"] == 10
    assert limit_sell["standing_quantity"] == 0
    assert limit_sell["open_quantity"] == 10
