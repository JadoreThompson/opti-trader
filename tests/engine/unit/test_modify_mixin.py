import pytest

from unittest.mock import Mock, MagicMock
from src.engine.mixins import ModifyOrderMixin

from src.engine.models import ModifyOrderCommand, MODIFY_SENTINEL
from src.enums import OrderType, Side


class DummyModifier(ModifyOrderMixin):
    """A dummy class to test the mixin's methods in isolation."""
    pass


@pytest.fixture
def modifier():
    return DummyModifier()


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.orderbook = MagicMock()
    return ctx


@pytest.mark.parametrize(
    "order_type, entry_price, details, expected",
    [
        (
            OrderType.LIMIT,
            100.0,
            ModifyOrderCommand(order_id="1", symbol="S", limit_price=105.0),
            105.0,
        ),
        (
            OrderType.STOP,
            100.0,
            ModifyOrderCommand(order_id="1", symbol="S", stop_price=95.0),
            95.0,
        ),
        (
            OrderType.LIMIT,
            100.0,
            ModifyOrderCommand(order_id="1", symbol="S", stop_price=95.0),
            100.0,
        ),  # Wrong type
        (
            OrderType.LIMIT,
            100.0,
            ModifyOrderCommand(order_id="1", symbol="S"),
            100.0,
        ),  # No change
    ],
)
def test_get_modified_price(
    modifier, order_factory, order_type, entry_price, details, expected
):
    """Test logic for determining the new price of a modified order."""
    order = order_factory(order_type=order_type, price=entry_price)
    result = modifier._get_modified_price(details, order)
    assert result == expected


def test_validate_modify_valid(modifier, mock_context, order_factory):
    """Test that a valid modification passes validation."""
    # A limit buy below the market price is valid
    mock_context.orderbook.price = 100.0
    order = order_factory(order_type=OrderType.LIMIT, side=Side.BID, price=90.0)
    details = ModifyOrderCommand(order_id="1", symbol="S", limit_price=95.0)

    assert modifier._validate_modify(details, order, mock_context) is True


def test_validate_modify_invalid_limit_cross(modifier, mock_context, order_factory):
    """Test that modifying a limit order to a crossing price is invalid."""
    mock_context.orderbook.price = 100.0
    order = order_factory(order_type=OrderType.LIMIT, side=Side.BID, price=90.0)
    details = ModifyOrderCommand(order_id="1", symbol="S", limit_price=105.0)

    assert modifier._validate_modify(details, order, mock_context) is False


def test_modify_order_valid(modifier, mock_context, order_factory):
    """Test the full _modify_order flow for a valid modification."""
    mock_context.orderbook.price = 100.0
    order = order_factory(order_type=OrderType.LIMIT, side=Side.BID, price=90.0)
    details = ModifyOrderCommand(order_id="1", symbol="S", limit_price=95.0)

    modifier._modify_order(details, order, mock_context)

    # Verify that the order book was updated
    mock_context.orderbook.remove.assert_called_once_with(order, 90.0)
    assert order.price == 95.0
    mock_context.orderbook.append.assert_called_once_with(order, 95.0)


def test_modify_order_invalid(modifier, mock_context, order_factory):
    """Test that an invalid modification does not alter the order book."""
    mock_context.orderbook.price = 100.0
    order = order_factory(order_type=OrderType.LIMIT, side=Side.BID, price=90.0)
    # This modification will cross the market price, so it's invalid
    details = ModifyOrderCommand(order_id="1", symbol="S", limit_price=101.0)

    modifier._modify_order(details, order, mock_context)

    # The order book should not be touched
    mock_context.orderbook.remove.assert_not_called()
    mock_context.orderbook.append.assert_not_called()
    assert order.price == 90.0
