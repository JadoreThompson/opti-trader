from enum import Enum


class OrderType(str, Enum):
    """All order types allowed within the DB"""
    MARKET = 'market_order'
    LIMIT = 'limit_order'
    CLOSE = 'close_order'
    MODIFY = 'modify_order'
    
    
class OrderStatus(str, Enum):
    """
    Represents the various statuses an order can have in the system.
    """
    # The order has been completely filled.
    FILLED = 'filled'

    # The order has been partially filled but still has remaining quantity.
    PARTIALLY_FILLED = 'partially_filled'

    # The order has not been filled at all.
    NOT_FILLED = 'not_filled'

    # The order has been closed and is no longer active.
    CLOSED = 'closed'

    # The order has some quantity remaining, but it is now inactive 
    # The client cannot perform any action on it.
    PARTIALLY_CLOSED_INACTIVE = 'partially_closed_inactive'

    # The order has remaining quantity to be consumed but can still be 
    # called for a CLOSE request.
    PARTIALLY_CLOSED_ACTIVE = 'partially_closed_active'

    # The contract has reached it's expiry date
    EXPIRED = 'expired'


class PubSubCategory(str, Enum):
    """
    All types of consumer message topics sent by the matching
    engine.
    """
    # Order was successfully placed, either a Limit or Market order
    SUCCESS = 'success'
    
    # Used to update the user on the status of an order, 
    # such as a partially filled order.
    # To be used without passing of the order details
    # if you want to pass the order object, you can use
    # ORDER_UPDATE
    UPDATE = 'update'
    
    # Used when a property of an order changes
    ORDER_UPDATE = 'order_update'
    
    # Indicates that an action cannot be performed.
    # For example, insufficient asks to execute a market order.
    ERROR = 'error'
    
    # Represents a new price update for a ticker.
    PRICE_UPDATE = 'price'
    
    # Represents an update in the DOM
    DOM_UPDATE = 'dom'
    
    # A general-purpose identifier for notifications. Currently used to notify 
    # users of events like someone they are copy trading performing an order. 
    # Kept generic for potential future use cases.
    NOTIFICATION = 'notification'


class UpdateScope(str, Enum):
    """Context of the update operation"""
    EXISTING = 'existing'
    NEW = 'new'
    
    
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


class Side(str, Enum):
    LONG = 'long'
    SHORT = 'short'
    
    def invert(self):
        return Side.SHORT if self == Side.LONG else Side.LONG

class MarketType(str, Enum):
    """Different types of markets the user can enter positions in """
    FUTURES = 'futures'
    SPOT = 'spot'
    
class PnlCategory(str, Enum):
    REALISED = 'realised'
    UNREALISED = 'unrealised'