import pytest
import uuid

from src.enums import OrderType, Side, StrategyType
from src.engine.models import (
    Command,
    NewOrderCommand,
    NewSingleOrder,
    CancelOrderCommand,
    ModifyOrderCommand,
)
from src.engine.enums import CommandType, MatchOutcome


def test_new_single_limit_order_non_matching(spot_engine, execution_context):
    """
    Test placing a single limit order that doesn't cross the spread.
    It should be added to the order book.
    """
    order_id = str(uuid.uuid4())
    order_data = {
        "order_id": order_id,
        "user_id": "user_maker_1",
        "order_type": OrderType.LIMIT,
        "side": Side.BID,
        "quantity": 10,
        "limit_price": 95.0,
    }

    cmd_data = NewSingleOrder(
        strategy_type=StrategyType.SINGLE,
        instrument_id="BTC-USD",
        order=order_data,
    )

    command = Command(command_type=CommandType.NEW_ORDER, data=cmd_data)
    spot_engine.process_command(command)

    # Verify order is in the book and store
    order_book = execution_context.orderbook
    order_store = execution_context.order_store

    assert order_book.best_bid == 95.0
    assert order_store.get(order_id) is not None
    assert order_store.get(order_id).quantity == 10


def test_order_matching_full_fill(spot_engine, execution_context):
    """
    Test a full match between a SINGLE taker and a SINGLE maker order.
    """
    # Place a maker order
    maker_order_id = str(uuid.uuid4())
    maker_data = {
        "order_id": maker_order_id,
        "user_id": "user_maker_1",
        "order_type": OrderType.LIMIT,
        "side": Side.ASK,
        "quantity": 50,
        "limit_price": 101.0,
    }
    maker_cmd = Command(
        command_type=CommandType.NEW_ORDER,
        data=NewSingleOrder(
            strategy_type=StrategyType.SINGLE, instrument_id="BTC-USD", order=maker_data
        ),
    )
    spot_engine.process_command(maker_cmd)

    # Place a crossing taker order
    taker_order_id = str(uuid.uuid4())
    taker_data = {
        "order_id": taker_order_id,
        "user_id": "user_taker",
        "order_type": OrderType.LIMIT,
        "side": Side.BID,
        "quantity": 50,
        "limit_price": 102.0,  # Crosses the 101 ask
    }
    taker_cmd = Command(
        command_type=CommandType.NEW_ORDER,
        data=NewSingleOrder(
            strategy_type=StrategyType.SINGLE, instrument_id="BTC-USD", order=taker_data
        ),
    )
    spot_engine.process_command(taker_cmd)

    order_book = execution_context.orderbook
    order_store = execution_context.order_store
    balance_manager = execution_context.balance_manager

    assert order_store.get(maker_order_id) is None
    assert not order_book.asks
    assert order_store.get(taker_order_id) is None

    assert balance_manager.get_balance("user_taker") == 50  # Taker bought 50
    assert balance_manager.get_balance("user_maker_1") == 0  # Maker sold 50


def test_order_matching_partial_fill(spot_engine, execution_context):
    """
    Test a partial match where the SINGLE taker order is larger than the
    SINGLE maker order.
    """
    # Place maker order
    maker_order_id = str(uuid.uuid4())
    maker_data = {
        "order_id": maker_order_id,
        "user_id": "user_maker_1",
        "order_type": OrderType.LIMIT,
        "side": Side.ASK,
        "quantity": 30,
        "limit_price": 101.0,
    }
    spot_engine.process_command(
        Command(
            command_type=CommandType.NEW_ORDER,
            data=NewSingleOrder(
                strategy_type=StrategyType.SINGLE,
                instrument_id="BTC-USD",
                order=maker_data,
            ),
        )
    )

    # Place larger taker order
    taker_order_id = str(uuid.uuid4())
    taker_data = {
        "order_id": taker_order_id,
        "user_id": "user_taker",
        "order_type": OrderType.LIMIT,
        "side": Side.BID,
        "quantity": 50,
        "limit_price": 102.0,
    }
    spot_engine.process_command(
        Command(
            command_type=CommandType.NEW_ORDER,
            data=NewSingleOrder(
                strategy_type=StrategyType.SINGLE,
                instrument_id="BTC-USD",
                order=taker_data,
            ),
        )
    )

    order_book = execution_context.orderbook
    order_store = execution_context.order_store

    # Maker order is filled and gone
    assert order_store.get(maker_order_id) is None
    assert not order_book.asks

    # Taker order is partially filled and now rests on the book
    taker_order = order_store.get(taker_order_id)
    assert taker_order is not None
    assert taker_order.executed_quantity == 30
    assert taker_order.quantity == 50
    assert order_book.best_bid == 102.0


def test_cancel_order(spot_engine, execution_context):
    """Test cancelling an active order."""
    # Place an order
    order_id = str(uuid.uuid4())
    order_data = {
        "order_id": order_id,
        "user_id": "user_maker_1",
        "order_type": OrderType.LIMIT,
        "side": Side.BID,
        "quantity": 10,
        "limit_price": 95.0,
    }
    spot_engine.process_command(
        Command(
            command_type=CommandType.NEW_ORDER,
            data=NewSingleOrder(
                strategy_type=StrategyType.SINGLE,
                instrument_id="BTC-USD",
                order=order_data,
            ),
        )
    )

    assert execution_context.order_store.get(order_id) is not None
    assert execution_context.orderbook.best_bid == 95.0

    # Cancel the order
    cancel_cmd = Command(
        command_type=CommandType.CANCEL_ORDER,
        data=CancelOrderCommand(order_id=order_id, symbol="BTC-USD"),
    )
    spot_engine.process_command(cancel_cmd)

    assert execution_context.order_store.get(order_id) is None
    assert execution_context.orderbook.best_bid is None


def test_modify_order(spot_engine, execution_context):
    """Test modifying an active order's price."""
    # Place an order
    order_id = str(uuid.uuid4())
    order_data = {
        "order_id": order_id,
        "user_id": "user_maker_1",
        "order_type": OrderType.LIMIT,
        "side": Side.BID,
        "quantity": 10,
        "limit_price": 95.0,
    }
    spot_engine.process_command(
        Command(
            command_type=CommandType.NEW_ORDER,
            data=NewSingleOrder(
                strategy_type=StrategyType.SINGLE,
                instrument_id="BTC-USD",
                order=order_data,
            ),
        )
    )
    assert execution_context.orderbook.best_bid == 95.0

    # Modify the order price
    modify_cmd = Command(
        command_type=CommandType.MODIFY_ORDER,
        data=ModifyOrderCommand(order_id=order_id, symbol="BTC-USD", limit_price=96.0),
    )
    spot_engine.process_command(modify_cmd)

    order_book = execution_context.orderbook
    assert order_book.best_bid == 96.0
    assert list(order_book.get_orders(95.0, Side.BID)) == []
    assert list(order_book.get_orders(96.0, Side.BID))[0].id == order_id
