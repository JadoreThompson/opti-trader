import pytest

from unittest.mock import MagicMock

from src.engine.models import NewOCOOrder, ModifyOrderCommand
from src.engine.orders import OCOOrder
from src.engine.strategies import OCOStrategy
from src.enums import OrderType, Side, StrategyType


@pytest.fixture
def oco_strategy():
    """Returns an OCOStrategy instance."""
    return OCOStrategy()


# def test_handle_new(oco_strategy, mock_context):
def test_handle_new(oco_strategy, execution_context):
    """
    Test handling a new OCO order.
    Both legs should be created and added to the book and store.
    """
    leg_a_data = {
        "order_id": "a1",
        "user_id": "u1",
        "order_type": OrderType.LIMIT,
        "side": Side.BID,
        "quantity": 10,
        "limit_price": 105.0,
    }
    leg_b_data = {
        "order_id": "b1",
        "user_id": "u1",
        "order_type": OrderType.STOP,
        "side": Side.BID,
        "quantity": 10,
        "stop_price": 95.0,
    }
    details = NewOCOOrder(
        strategy_type=StrategyType.OCO, instrument_id="S", legs=[leg_a_data, leg_b_data]
    )

    oco_strategy.handle_new(details, execution_context)

    assert execution_context.order_store.get(
        "a1"
    ).counterparty == execution_context.order_store.get("b1")


def test_handle_filled_fully(oco_strategy, mock_execution_context):
    """
    Test that a fully filled OCO leg cancels its counterparty.
    """
    order_a = OCOOrder(
        id_="a1",
        user_id="u1",
        strategy_type=StrategyType.OCO,
        order_type=OrderType.LIMIT,
        side=Side.ASK,
        quantity=10,
        price=105.0,
    )
    order_b = OCOOrder(
        id_="b1",
        user_id="u1",
        strategy_type=StrategyType.OCO,
        order_type=OrderType.STOP,
        side=Side.ASK,
        quantity=10,
        price=95.0,
    )
    order_a.counterparty = order_b
    order_b.counterparty = order_a
    order_a.executed_quantity = 10  # Mark as filled

    oco_strategy.handle_filled(10, 105.0, order_a, mock_execution_context)

    # Should remove both orders from book and store
    assert mock_execution_context.orderbook.remove.call_count == 2
    assert mock_execution_context.order_store.remove.call_count == 2
    mock_execution_context.orderbook.remove.assert_any_call(order_a, 105.0)
    mock_execution_context.orderbook.remove.assert_any_call(order_b, 95.0)


def test_handle_filled_partially(oco_strategy, mock_execution_context):
    """
    Test that a partially filled OCO leg does not cancel its counterparty.
    """
    order_a = OCOOrder(
        id_="a1",
        user_id="u1",
        strategy_type=StrategyType.OCO,
        order_type=OrderType.LIMIT,
        side=Side.ASK,
        quantity=10,
        price=105.0,
    )
    order_a.executed_quantity = 5

    oco_strategy.handle_filled(5, 105.0, order_a, mock_execution_context)

    mock_execution_context.orderbook.remove.assert_not_called()
    mock_execution_context.order_store.remove.assert_not_called()


# @pytest.mark.skip(reason="Requires fix for buggy modify method in OCOStrategy")
def test_modify(oco_strategy, mock_execution_context):
    """
    Test modifying an OCO leg's price.
    """
    mock_execution_context.orderbook.price = 100.0
    order = OCOOrder(
        id_="a1",
        user_id="u1",
        strategy_type=StrategyType.OCO,
        order_type=OrderType.LIMIT,
        side=Side.ASK,
        quantity=10,
        price=105.0,
    )
    details = ModifyOrderCommand(order_id="a1", symbol="S", limit_price=106.0)

    oco_strategy.modify(details, order, mock_execution_context)

    mock_execution_context.orderbook.remove.assert_called_once_with(order, 105.0)
    assert order.price == 106.0
    mock_execution_context.orderbook.append.assert_called_once_with(order, 106.0)
