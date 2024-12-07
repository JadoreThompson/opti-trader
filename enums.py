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
    
    # The order has quantity that needs to be closed, this can't be closed again
    PARTIALLY_CLOSED = 'partially_closed'

    # The order still has some quantity that can be closed
    PARTIALLY_CLOSED_ACTIVE = 'partially_closed_active'


class _OrderType(int, Enum):
    """
    Within the Matching engine, to allow tracking and differentation
    of order types we have these types as an added key:pair
    """    
    MARKET_ORDER = 0
    LIMIT_ORDER = 1
    STOP_LOSS_ORDER = 2
    TAKE_PROFIT_ORDER = 3
    CLOSE_ORDER = 4

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
