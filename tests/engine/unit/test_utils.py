import pytest

from unittest.mock import Mock

from src.enums import OrderType, Side
from src.engine.utils import get_price_key, limit_crossable, stop_crossable


def test_get_price_key():
    """Test that the correct price key is returned for each order type."""
    assert get_price_key(OrderType.LIMIT) == "limit_price"
    assert get_price_key(OrderType.STOP) == "stop_price"
    assert get_price_key(OrderType.MARKET) == "price"
    assert get_price_key("invalid_type") is None


@pytest.mark.parametrize(
    "price, side, ob_price, expected",
    [
        (101, Side.BID, 100, True),  # Buy limit above market price -> cross
        (99, Side.BID, 100, False),  # Buy limit below market price -> no cross
        (99, Side.ASK, 100, True),  # Sell limit below market price -> cross
        (101, Side.ASK, 100, False),  # Sell limit above market price -> no cross
        (100, Side.BID, 100, True),  # At the money
        (100, Side.ASK, 100, True),  # At the money
    ],
)
def test_limit_crossable(price, side, ob_price, expected):
    """Test the limit_crossable utility function."""
    mock_ob = Mock()
    mock_ob.price = ob_price
    assert limit_crossable(price, side, mock_ob) == expected


@pytest.mark.parametrize(
    "price, side, ob_price, expected",
    [
        (99, Side.BID, 100, True),  # Buy stop below market price -> cross
        (101, Side.BID, 100, False),  # Buy stop above market price -> no cross
        (101, Side.ASK, 100, True),  # Sell stop above market price -> cross
        (99, Side.ASK, 100, False),  # Sell stop below market price -> no cross
        (100, Side.BID, 100, True),  # At the money
        (100, Side.ASK, 100, True),  # At the money
    ],
)
def test_stop_crossable(price, side, ob_price, expected):
    """Test the stop_crossable utility function."""
    mock_ob = Mock()
    mock_ob.price = ob_price
    assert stop_crossable(price, side, mock_ob) == expected
