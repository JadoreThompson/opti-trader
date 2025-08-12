import pytest
from unittest.mock import MagicMock, patch

from src.engine.enums import MatchOutcome
from src.engine.models import NewOTOCOOrder
from src.engine.orders import OTOCOOrder
from src.engine.strategies import OTOCOStrategy
from src.engine.typing import MatchResult
from src.enums import OrderType, Side, StrategyType


@pytest.fixture
def otoco_strategy():
    """Returns an OTOCOStrategy instance."""
    return OTOCOStrategy()


def test_handle_new_parent_not_matching(otoco_strategy, mock_execution_context):
    """
    Test creating an OTOCO where the parent does not immediately fill.
    The parent is added to book; all three orders are added to store.
    """
    parent_data = {
        "order_id": "p1",
        "user_id": "u1",
        "order_type": OrderType.LIMIT,
        "side": Side.BID,
        "quantity": 10,
        "limit_price": 99.0,
    }
    leg_a_data = {
        "order_id": "a1",
        "user_id": "u1",
        "order_type": OrderType.LIMIT,
        "side": Side.ASK,
        "quantity": 10,
        "limit_price": 105.0,
    }
    leg_b_data = {
        "order_id": "b1",
        "user_id": "u1",
        "order_type": OrderType.STOP,
        "side": Side.ASK,
        "quantity": 10,
        "stop_price": 95.0,
    }
    details = NewOTOCOOrder(
        strategy_type=StrategyType.OTOCO,
        instrument_id="S",
        parent=parent_data,
        oco_legs=[leg_a_data, leg_b_data],
    )

    with patch(
        "src.engine.strategies.otoco_strategy.limit_crossable", return_value=False
    ):
        otoco_strategy.handle_new(details, mock_execution_context)

    mock_execution_context.engine.match.assert_not_called()
    mock_execution_context.orderbook.append.assert_called_once()
    assert mock_execution_context.orderbook.append.call_args[0][0].id == "p1"
    assert mock_execution_context.order_store.add.call_count == 3


def test_handle_new_parent_fully_matching(otoco_strategy, mock_execution_context):
    """
    Test an OTOCO where the parent immediately fills, triggering the OCO children.
    """
    parent_data = {
        "order_id": "p1",
        "user_id": "u1",
        "order_type": OrderType.LIMIT,
        "side": Side.BID,
        "quantity": 10,
        "limit_price": 101.0,
    }
    leg_a_data = {
        "order_id": "a1",
        "user_id": "u1",
        "order_type": OrderType.LIMIT,
        "quantity": 10,
        "side": Side.ASK,
        "limit_price": 105.0,
    }
    leg_b_data = {
        "order_id": "b1",
        "user_id": "u1",
        "order_type": OrderType.STOP,
        "side": Side.ASK,
        "quantity": 10,
        "stop_price": 95.0,
    }
    details = NewOTOCOOrder(
        strategy_type=StrategyType.OTOCO,
        instrument_id="S",
        parent=parent_data,
        oco_legs=[leg_a_data, leg_b_data],
    )

    mock_execution_context.engine.match.return_value = MatchResult(
        MatchOutcome.SUCCESS, 10, 100.5
    )
    with patch(
        "src.engine.strategies.otoco_strategy.limit_crossable", return_value=True
    ):
        otoco_strategy.handle_new(details, mock_execution_context)

    mock_execution_context.engine.match.assert_called_once()
    assert mock_execution_context.orderbook.append.call_count == 2
    mock_execution_context.order_store.remove.assert_called_once()
    assert mock_execution_context.order_store.remove.call_args[0][0].id == "p1"


def test_handle_filled_parent(otoco_strategy, mock_execution_context):
    """
    Test that a filled parent triggers its OCO children.
    """
    parent = OTOCOOrder(
        id_="p1",
        user_id="u1",
        strategy_type=StrategyType.OTOCO,
        order_type=OrderType.LIMIT,
        side=Side.BID,
        quantity=10,
        price=99.0,
    )
    child_a = OTOCOOrder(
        id_="a1",
        user_id="u1",
        strategy_type=StrategyType.OTOCO,
        order_type=OrderType.LIMIT,
        side=Side.ASK,
        quantity=10,
        price=105.0,
        parent=parent,
    )
    child_b = OTOCOOrder(
        id_="b1",
        user_id="u1",
        strategy_type=StrategyType.OTOCO,
        order_type=OrderType.STOP,
        side=Side.ASK,
        quantity=10,
        price=95.0,
        parent=parent,
    )
    parent.child_a = child_a
    parent.child_b = child_b
    parent.executed_quantity = 10

    otoco_strategy.handle_filled(10, 100.0, parent, mock_execution_context)

    assert mock_execution_context.orderbook.append.call_count == 2
    mock_execution_context.order_store.remove.assert_called_once_with(parent)
    assert child_a.triggered is True
    assert child_b.triggered is True


def test_handle_filled_child(otoco_strategy, mock_execution_context):
    """
    Test that a filled OCO child cancels its counterparty.
    """
    child_a = OTOCOOrder(
        id_="a1",
        user_id="u1",
        strategy_type=StrategyType.OTOCO,
        order_type=OrderType.LIMIT,
        side=Side.ASK,
        quantity=10,
        price=105.0,
    )
    child_b = OTOCOOrder(
        id_="b1",
        user_id="u1",
        strategy_type=StrategyType.OTOCO,
        order_type=OrderType.STOP,
        side=Side.ASK,
        quantity=10,
        price=95.0,
    )
    child_a.counterparty = child_b
    child_b.counterparty = child_a
    child_a.executed_quantity = 10  # Mark as filled

    otoco_strategy.handle_filled(10, 105.0, child_a, mock_execution_context)

    mock_execution_context.orderbook.remove.assert_called_once_with(child_b, 95.0)
    assert mock_execution_context.order_store.remove.call_count == 2
    mock_execution_context.order_store.remove.assert_any_call(child_a)
    mock_execution_context.order_store.remove.assert_any_call(child_b)


def test_cancel_parent(otoco_strategy, mock_execution_context):
    """
    Test that canceling an untriggered parent cancels all three legs.
    """
    parent = OTOCOOrder(
        id_="p1",
        user_id="u1",
        strategy_type=StrategyType.OTOCO,
        order_type=OrderType.LIMIT,
        side=Side.BID,
        quantity=10,
        price=99.0,
    )
    child_a = OTOCOOrder(
        id_="a1",
        user_id="u1",
        strategy_type=StrategyType.OTOCO,
        order_type=OrderType.LIMIT,
        side=Side.ASK,
        quantity=10,
        price=105.0,
        parent=parent,
    )
    child_b = OTOCOOrder(
        id_="b1",
        user_id="u1",
        strategy_type=StrategyType.OTOCO,
        order_type=OrderType.STOP,
        side=Side.ASK,
        quantity=10,
        price=95.0,
        parent=parent,
    )
    parent.child_a = child_a
    parent.child_b = child_b

    otoco_strategy.cancel(parent, mock_execution_context)

    mock_execution_context.orderbook.remove.assert_called_once_with(parent, 99.0)
    assert mock_execution_context.order_store.remove.call_count == 3
