from enum import Enum


class OrderType(str, Enum):
    MARKET = 'market_order'
    LIMIT = 'limit_order'
    CLOSE = 'close_order'
    
    TAKE_PROFIT_CHANGE = 'take_profit_change'
    STOP_LOSS_CHANGE = 'stop_loss_change'
    ENTRY_PRICE_CHANGE = 'entry_price_change'


class OrderStatus(str, Enum):
    FILLED = 'filled'
    PARTIALLY_FILLED = 'partially_filled'
    NOT_FILLED = 'not_filled'
    CLOSED = 'closed'
    PARTIALLY_CLOSED = 'partially_closed'


class _InternalOrderType(str, Enum):
    MARKET_ORDER = 'market_order'
    STOP_LOSS_ORDER = 'stop_loss_order'
    TAKE_PROFIT_ORDER = 'take_profit_order'


class ConsumerStatusType (str, Enum):
    SUCCESS = 'success',
    UPDATE = 'update',
    ERROR = 'error'
    