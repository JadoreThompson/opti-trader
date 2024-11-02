from enum import Enum


class OrderType(str, Enum):
    MARKET = 'market_order'
    LIMIT = 'limit_order'
    CLOSE = 'close_order'


class OrderStatus(str, Enum):
    FILLED = 'filled'
    PARTIALLY_FILLED = 'partially_filled'
    NOT_FILLED = 'not_filled'
    CLOSED = 'closed'
    PARTIALLY_CLOSED = 'partially_closed'
