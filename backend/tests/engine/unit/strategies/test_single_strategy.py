import pytest
from unittest.mock import MagicMock, patch

from src.engine.enums import MatchOutcome
from src.engine.models import NewSingleOrder
from src.engine.strategies import SingleOrderStrategy
from src.engine.typing import MatchResult
from src.enums import OrderType, Side, StrategyType


@pytest.fixture
def single_strategy():
    return SingleOrderStrategy()


def test_handle_new_non_matching(
    single_strategy, mock_execution_context, order_factory
):
    """Test handling a new single order that doesn't immediately match."""
    order_data = {
        "order_id": "1",
        "user_id": "u1",
        "order_type": OrderType.LIMIT,
        "side": Side.BID,
        "quantity": 100,
        "limit_price": 99.0,
    }
    details = NewSingleOrder(
        strategy_type=StrategyType.SINGLE, instrument_id="S", order=order_data
    )

    # Simulate a non-crossing price
    with patch(
        "src.engine.strategies.single_strategy.limit_crossable", return_value=False
    ):
        single_strategy.handle_new(details, mock_execution_context)

    # Assert that the order was added to the store and book
    mock_execution_context.order_store.add.assert_called_once()
    mock_execution_context.orderbook.append.assert_called_once()
    mock_execution_context.engine.match.assert_not_called()


def test_handle_new_matching_and_fail(
    single_strategy, mock_execution_context, order_factory
):
    """Test a new order that matches but is not fully filled."""
    order_data = {
        "order_id": "1",
        "user_id": "u1",
        "order_type": OrderType.LIMIT,
        "side": Side.BID,
        "quantity": 100,
        "limit_price": 101.0,
    }
    details = NewSingleOrder(
        strategy_type=StrategyType.SINGLE, instrument_id="S", order=order_data
    )

    # Simulate a crossing price and a partial fill
    mock_execution_context.engine.match.return_value = MatchResult(
        MatchOutcome.PARTIAL, 50, 100.5
    )
    with patch(
        "src.engine.strategies.single_strategy.limit_crossable", return_value=True
    ):
        single_strategy.handle_new(details, mock_execution_context)

    # Assert match was called and the partially filled order was added to the book
    mock_execution_context.engine.match.assert_called_once()
    mock_execution_context.order_store.add.assert_called_once()
    mock_execution_context.orderbook.append.assert_called_once()


def test_handle_filled_fully(single_strategy, mock_execution_context, order_factory):
    """Test that a fully filled order is removed from the store."""
    order = order_factory(quantity=100)
    order.executed_quantity = 100  # Mark as fully filled

    single_strategy.handle_filled(100, 100.0, order, mock_execution_context)

    mock_execution_context.order_store.remove.assert_called_once_with(order)


def test_handle_filled_partially(
    single_strategy, mock_execution_context, order_factory
):
    """Test that a partially filled order is not removed."""
    order = order_factory(quantity=100)
    order.executed_quantity = 50  # Mark as partially filled

    single_strategy.handle_filled(50, 100.0, order, mock_execution_context)

    mock_execution_context.order_store.remove.assert_not_called()


def test_cancel_order(single_strategy, mock_execution_context, order_factory):
    """Test that canceling an order removes it from the book and store."""
    order = order_factory(price=99.0)

    single_strategy.cancel(order, mock_execution_context)

    mock_execution_context.orderbook.remove.assert_called_once_with(order, 99.0)
    mock_execution_context.order_store.remove.assert_called_once_with(order)
