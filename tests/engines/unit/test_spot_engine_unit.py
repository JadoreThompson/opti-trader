import pytest
from engine import SpotEngine
from engine.orderbook import OrderBook
from engine.typing import CloseRequest, ModifyRequest
from enums import OrderStatus, OrderType, Side
from tests.mocks import MockOCOManager
from tests.utils import create_order_simple


@pytest.fixture
def engine():
    """Provides a clean instance of the SpotEngine for each test."""
    return SpotEngine()


@pytest.fixture(scope="module")
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


def test_market_bid_gets_filled(engine):
    """
    Scenario: A resting limit sell is fully filled by an incoming market buy.
    """
    instrument = "abc"
    engine._orderbooks.setdefault(instrument, OrderBook())

    # Setting up resting order
    ask_limit = create_order_simple(
        "sell1",
        Side.ASK,
        OrderType.LIMIT,
        quantity=10,
        limit_price=100.0,
        instrument=instrument,
    )
    ask_limit["user_id"] = "jeff"
    engine._balance_manager._users[ask_limit["user_id"]] = 100
    engine.place_order(ask_limit)

    market_buy = create_order_simple(
        "buy1", Side.BID, OrderType.MARKET, quantity=10, instrument=instrument
    )

    engine.place_order(market_buy)
    assert market_buy["open_quantity"] == 10
    assert market_buy["standing_quantity"] == 0


@pytest.mark.asyncio
async def test_market_bid_and_limit_ask_neutralise(engine: SpotEngine):
    """
    Scenario: A limit bid is placed into an empty book as a resting order.
        An aggressive ASK market order comes in and takes out the limit
        bid as it rests at the best bid price.
    """
    limit_sell = create_order_simple(
        "sell1",
        Side.ASK,
        OrderType.LIMIT,
        quantity=10,
        limit_price=100.0,
    )
    engine._balance_manager._users[limit_sell["user_id"]] = 10

    market_buy = create_order_simple("buy1", Side.BID, OrderType.MARKET, quantity=10)

    engine.place_order(limit_sell)
    engine.place_order(market_buy)

    assert market_buy["standing_quantity"] == 0
    assert market_buy["open_quantity"] == 10
    assert limit_sell["standing_quantity"] == 0
    assert limit_sell["open_quantity"] == 10


def test_full_position_close():
    """
    Scenario: A limit bid is filled by a market ask order. TP and SL
        should then be placed. A market bid comes in and hits the SL.
        BalanceManger should remove the payload and the OCOManager should
        discard of the OCOOrder.
    """
    mock_oco_manager = MockOCOManager()
    engine = SpotEngine(oco_manager=mock_oco_manager)
    balance_manager = engine._balance_manager
    instrument = "ticker"

    limit_bid = create_order_simple(
        "buy1",
        Side.BID,
        OrderType.LIMIT_OCO,
        quantity=10,
        limit_price=100.0,
        sl_price=50.0,
        tp_price=150.0,
        instrument=instrument,
    )
    market_sell = create_order_simple(
        "sell1",
        Side.ASK,
        OrderType.MARKET,
        quantity=10,
        open_quantity=0,
        instrument=instrument,
    )

    balance_manager._users[market_sell["user_id"]] = market_sell["quantity"]

    engine.place_order(limit_bid)
    engine.place_order(market_sell)

    ob = engine._orderbooks[instrument]

    assert limit_bid["standing_quantity"] == 0
    assert limit_bid["open_quantity"] == 10

    assert market_sell["standing_quantity"] == 0
    assert market_sell["open_quantity"] == 10
    assert balance_manager.get_balance(market_sell["user_id"]) is None

    assert ob.best_ask == 50.0
    assert ob.asks[50.0].head == ob.asks[50.0].tail

    market_bid = create_order_simple(
        "buy2",
        Side.BID,
        OrderType.MARKET,
        quantity=10,
        open_quantity=0,
        instrument=instrument,
    )

    engine.place_order(market_bid)

    assert market_bid["standing_quantity"] == 0
    assert market_bid["open_quantity"] == 10
    assert limit_bid["standing_quantity"] == 0
    assert limit_bid["open_quantity"] == 0

    assert balance_manager.get_balance(limit_bid["user_id"]) is None
    assert mock_oco_manager.get(limit_bid["oco_id"]) is None


def test_cancel_order(engine: SpotEngine):
    """
    Scenario: A limit bid is placed with no quantity consumed.
    Client submits two cancel request to reduce the quantity of the position
    with the first being a partial closure of 2 and the second being 'ALL'.
    """
    limit_bid = create_order_simple(
        "buy1", Side.BID, OrderType.LIMIT, quantity=10, limit_price=100.0
    )

    engine.place_order(limit_bid)

    cancel_request = CloseRequest("buy1", 2)
    engine.cancel_order(cancel_request)

    assert limit_bid["standing_quantity"] == 8
    assert limit_bid["open_quantity"] == 0

    cancel_request = CloseRequest("buy1", "ALL")
    engine.cancel_order(cancel_request)

    assert limit_bid["standing_quantity"] == 0
    assert limit_bid["open_quantity"] == 0
    assert engine._order_manager.get("buy") is None
    assert engine._balance_manager.get_balance(limit_bid["user_id"]) is None


def test_cancel_partially_filled_order(engine: SpotEngine):
    """
    Scenario: A limit bid is placed for quantity `qb` and a market
        ask is placed for quantity `qa`. The market ask partially fills
        the limit bid. The client then sends a series of cancel requests
        eroding the quantity until it's eventually removed from the engine
        due to the standing_quantity reaching 0 and having no OCO order to take
        care of.
    """
    limit_bid = create_order_simple(
        "buy1", Side.BID, OrderType.LIMIT, quantity=10, limit_price=100.0
    )
    market_sell = create_order_simple("sell1", Side.ASK, OrderType.MARKET, quantity=5)

    engine._balance_manager._users[market_sell["user_id"]] = market_sell["quantity"]
    engine.place_order(limit_bid)
    engine.place_order(market_sell)

    assert limit_bid["standing_quantity"] == 5
    assert limit_bid["open_quantity"] == 5
    assert market_sell["standing_quantity"] == 0
    assert market_sell["open_quantity"] == 5

    cancel_request = CloseRequest("buy1", 3)
    engine.cancel_order(cancel_request)

    assert limit_bid["standing_quantity"] == 2
    assert limit_bid["open_quantity"] == 5

    market_sell = create_order_simple("sell1", Side.ASK, OrderType.MARKET, quantity=1)
    engine._balance_manager._users[market_sell["user_id"]] = market_sell["quantity"]
    engine.place_order(market_sell)

    assert limit_bid["standing_quantity"] == 1
    assert limit_bid["open_quantity"] == 6

    cancel_request = CloseRequest("buy1", 1)
    engine.cancel_order(cancel_request)

    assert limit_bid["standing_quantity"] == 0
    assert limit_bid["open_quantity"] == 6
    assert engine._balance_manager.get_balance(limit_bid["user_id"]) is not None
    assert engine._order_manager.get("buy1") is None


def test_modify_order(engine: SpotEngine):
    """
    Scenario: A simple limit bid is submitted and the client
    sends 3 modify requests for limit, take profit and stop loss
    price.
    """
    limit_bid = create_order_simple(
        "buy1", Side.BID, OrderType.LIMIT, quantity=10, limit_price=100.0
    )
    engine.place_order(limit_bid)

    modify_request = ModifyRequest(order_id="buy1", limit_price=120.0)
    engine.modify_order(modify_request)

    assert (
        limit_bid["limit_price"] == 100.0
    )  # Limit price must be less that current price.

    modify_request = ModifyRequest(order_id="buy1", take_profit=200.0)
    engine.modify_order(modify_request)

    assert limit_bid["take_profit"] == None

    modify_request = ModifyRequest(order_id="buy1", stop_loss=100.0)
    engine.modify_order(modify_request)

    assert limit_bid["stop_loss"] == None


def test_modify_order_oco_order(engine: SpotEngine):
    """
    Scenario: An oco limit bid is submitted and the client
    sends 3 modify requests for limit, take profit and stop loss
    price.
    """
    limit_bid = create_order_simple(
        "buy1",
        Side.BID,
        OrderType.LIMIT_OCO,
        quantity=10,
        limit_price=100.0,
        tp_price=150.0,
        sl_price=50.0,
    )
    engine.place_order(limit_bid)

    modify_request = ModifyRequest(order_id="buy1", limit_price=80.0)
    engine.modify_order(modify_request)

    assert limit_bid["limit_price"] == 80.0

    modify_request = ModifyRequest(order_id="buy1", take_profit=200.0)
    engine.modify_order(modify_request)

    assert limit_bid["take_profit"] == 200.0

    modify_request = ModifyRequest(order_id="buy1", stop_loss=70.0)
    engine.modify_order(modify_request)

    assert limit_bid["stop_loss"] == 70.0


def test_modify_order_filled_order(engine: SpotEngine):
    """
    Scenario: An oco limit bid is submitted and filled and the client
    sends 3 modify requests for limit, take profit and stop loss
    price. Only the take profit and stop loss modifications should succeed.
    """
    limit_bid = create_order_simple(
        "buy1",
        Side.BID,
        OrderType.LIMIT_OCO,
        quantity=10,
        limit_price=100.0,
        tp_price=150.0,
        sl_price=50.0,
    )

    market_sell = create_order_simple(
        "sell1",
        Side.ASK,
        OrderType.MARKET,
        quantity=10,
    )
    engine._balance_manager._users[market_sell["user_id"]] = market_sell["quantity"]

    engine.place_order(limit_bid)
    engine.place_order(market_sell)

    modify_request = ModifyRequest(order_id="buy1", limit_price=120.0)
    engine.modify_order(modify_request)

    assert limit_bid["limit_price"] == 100.0

    modify_request = ModifyRequest(order_id="buy1", take_profit=200.0)
    engine.modify_order(modify_request)

    assert limit_bid["take_profit"] == 200.0

    modify_request = ModifyRequest(order_id="buy1", stop_loss=100.0)
    engine.modify_order(modify_request)

    assert limit_bid["stop_loss"] == 100.0


def test_modify_order_partially_filled_order(engine: SpotEngine):
    """
    Scenario: An oco limit bid is submitted and partially filled the client
    sends 3 modify requests for limit, take profit and stop loss
    price. Of which all should succeed.
    """
    limit_bid = create_order_simple(
        "buy1",
        Side.BID,
        OrderType.LIMIT_OCO,
        quantity=10,
        limit_price=100.0,
        tp_price=150.0,
        sl_price=50.0,
    )

    market_sell = create_order_simple(
        "sell1",
        Side.ASK,
        OrderType.MARKET,
        quantity=5,
    )
    engine._balance_manager._users[market_sell["user_id"]] = market_sell["quantity"]

    engine.place_order(limit_bid)
    engine.place_order(market_sell)

    modify_request = ModifyRequest(order_id="buy1", limit_price=120.0)
    engine.modify_order(modify_request)

    assert limit_bid["limit_price"] == 100.0

    modify_request = ModifyRequest(order_id="buy1", take_profit=200.0)
    engine.modify_order(modify_request)

    assert limit_bid["take_profit"] == 200.0

    modify_request = ModifyRequest(order_id="buy1", stop_loss=90.0)
    engine.modify_order(modify_request)

    assert limit_bid["stop_loss"] == 90.0
