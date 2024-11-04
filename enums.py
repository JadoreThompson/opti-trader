from enum import Enum


class OrderType(str, Enum):
    MARKET = 'market_order'
    LIMIT = 'limit_order'
    CLOSE = 'close_order'
    TAKE_PROFIT_CHANGE = 'take_profit_change'
    STOP_LOSS_CHANGE = 'stop_loss_change'


class OrderStatus(str, Enum):
    FILLED = 'filled'
    PARTIALLY_FILLED = 'partially_filled'
    NOT_FILLED = 'not_filled'
    CLOSED = 'closed'
    PARTIALLY_CLOSED = 'partially_closed'
