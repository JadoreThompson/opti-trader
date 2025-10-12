import pytest

from unittest.mock import MagicMock, patch

from src.engine.strategies import OTOStrategy
from src.engine.models import NewOTOOrder
from src.enums import OrderType, Side, StrategyType
from src.engine.enums import MatchOutcome
from src.engine.typing import MatchResult
from src.engine.orders import OTOOrder


@pytest.fixture
def oto_strategy():
    return OTOStrategy()


def test_handle_new_parent_not_matching(oto_strategy, mock_execution_context):
    """Test creating an OTO where the parent does not immediately fill."""
    parent_data = {
        "order_id": "p1",
        "user_id": "u1",
        "order_type": OrderType.LIMIT,
        "side": Side.BID,
        "quantity": 10,
        "limit_price": 99.0,
    }
    child_data = {
        "order_id": "c1",
        "user_id": "u1",
        "order_type": OrderType.LIMIT,
        "side": Side.ASK,
        "quantity": 10,
        "limit_price": 105.0,
    }
    details = NewOTOOrder(
        strategy_type=StrategyType.OTO,
        instrument_id="S",
        parent=parent_data,
        child=child_data,
    )

    with patch(
        "src.engine.strategies.oto_strategy.limit_crossable", return_value=False
    ):
        oto_strategy.handle_new(details, mock_execution_context)

    # Parent is added to book, both added to store
    assert mock_execution_context.orderbook.append.call_count == 1
    assert (
        mock_execution_context.orderbook.append.call_args[0][0].id == "p1"
    )  # Parent order
    assert mock_execution_context.order_store.add.call_count == 2
    mock_execution_context.engine.match.assert_not_called()


def test_handle_new_parent_fully_matching(oto_strategy, mock_execution_context):
    """Test creating an OTO where the parent immediately fills, triggering the child."""
    parent_data = {
        "order_id": "p1",
        "user_id": "u1",
        "order_type": OrderType.LIMIT,
        "side": Side.BID,
        "quantity": 10,
        "limit_price": 101.0,
    }
    child_data = {
        "order_id": "c1",
        "user_id": "u1",
        "order_type": OrderType.LIMIT,
        "side": Side.ASK,
        "quantity": 10,
        "limit_price": 105.0,
    }
    details = NewOTOOrder(
        strategy_type=StrategyType.OTO,
        instrument_id="S",
        parent=parent_data,
        child=child_data,
    )

    mock_execution_context.engine.match.return_value = MatchResult(
        MatchOutcome.SUCCESS, 10, 100.5
    )
    with patch("src.engine.strategies.oto_strategy.limit_crossable", return_value=True):
        oto_strategy.handle_new(details, mock_execution_context)

    # Match is called, and child is added to the book
    mock_execution_context.engine.match.assert_called_once()
    assert mock_execution_context.orderbook.append.call_count == 1
    assert (
        mock_execution_context.orderbook.append.call_args[0][0].id == "c1"
    )  # Child order
    assert (
        mock_execution_context.order_store.add.call_count == 1
    )  # Only child gets added


def test_handle_filled_parent(oto_strategy, mock_execution_context):
    """Test that a filled parent triggers its child."""
    child = OTOOrder(
        id_="c1",
        user_id="u1",
        strategy_type=StrategyType.OTO,
        order_type=OrderType.LIMIT,
        side=Side.ASK,
        quantity=10,
        price=105.0,
    )
    parent = OTOOrder(
        id_="p1",
        user_id="u1",
        strategy_type=StrategyType.OTO,
        order_type=OrderType.LIMIT,
        side=Side.BID,
        quantity=10,
        price=99.0,
        child=child,
    )
    child.parent = parent

    parent.executed_quantity = 10  # Mark as filled

    oto_strategy.handle_filled(10, 100.0, parent, mock_execution_context)

    mock_execution_context.orderbook.append.assert_called_once_with(child, 105.0)
    mock_execution_context.order_store.remove.assert_called_once_with(parent)
    assert child.triggered is True


def test_cancel_parent(oto_strategy, mock_execution_context):
    """Test that canceling a parent also removes the child from the store."""
    child = OTOOrder(
        id_="c1",
        user_id="u1",
        strategy_type=StrategyType.OTO,
        order_type=OrderType.LIMIT,
        side=Side.ASK,
        quantity=10,
        price=105.0,
    )
    parent = OTOOrder(
        id_="p1",
        user_id="u1",
        strategy_type=StrategyType.OTO,
        order_type=OrderType.LIMIT,
        side=Side.BID,
        quantity=10,
        price=99.0,
        child=child,
    )

    oto_strategy.cancel(parent, mock_execution_context)

    mock_execution_context.orderbook.remove.assert_called_once_with(parent, 99.0)
    assert mock_execution_context.order_store.remove.call_count == 2  # Parent and child
