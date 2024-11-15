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
    """
    Within the Matching engine, to allow tracking and differentation
    of order types we have these types as an added key:pair
    """    
    MARKET_ORDER = 'market_order'
    STOP_LOSS_ORDER = 'stop_loss_order'
    TAKE_PROFIT_ORDER = 'take_profit_order'


class ConsumerStatusType(str, Enum):
    """
    All types of consumer message topics sent by the matching
    engine
    """    
    SUCCESS = 'success'
    UPDATE = 'update'
    ERROR = 'error'
    PRICE_UPDATE = 'price'
    
    
class IntervalTypes(str, Enum):
    """
    All types of intervals for market data the user
    can request
    """    
    H4 = '4h'
    M15 = '15m'
    M1 = '1m'
    
    def to_seconds(self):
        return {
            '4h': 14400,
            '15m': 900,
            '1m': 60
        }[self.value]


class GrowthInterval(str, Enum):
    DAY = '1d'
    WEEK = '1w'
    MONTH = '1m'
    YEAR = '1y'
    ALL = 'all'
