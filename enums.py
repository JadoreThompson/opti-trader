from enum import Enum


class OrderType(str, Enum):
    MARKET = 'market_order'
    LIMIT = 'limit_order'
    CLOSE = 'close_order'
    MODIFY = 'modify_order'


class OrderStatus(str, Enum):
    FILLED = 'filled'
    PARTIALLY_FILLED = 'partially_filled'
    NOT_FILLED = 'not_filled'
    CLOSED = 'closed'
    """
    Order still has quantity remaining for consumption.
    Objects with this OrderStatus can't be called within a CLOSE request
    again
    """
    PARTIALLY_CLOSED_INACTIVE = 'partially_closed_inactive'

    """
    Order still has remaining quantity to be consumed
    however it can still be called for a close request
    """
    PARTIALLY_CLOSED_ACTIVE = 'partially_closed_active'

class ConsumerMessageStatus(str, Enum):
    """
    All types of consumer message topics sent by the matching
    engine
    """    
    SUCCESS = 'success'
    UPDATE = 'update'
    ERROR = 'error'
    PRICE_UPDATE = 'price'
    NOTIFICATION = 'notification'
    
    
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
