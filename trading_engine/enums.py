from enum import Enum

class OrderType(int, Enum):
    """
    An extension of the order type class in the 
    parent folder. Specifically tailored for the matching engine
    with extended
    """
    MARKET_ORDER = 0
    LIMIT_ORDER = 1
    STOP_LOSS_ORDER = 2
    TAKE_PROFIT_ORDER = 3
    """An unplanned close request"""
    CLOSE_ORDER = 4


class Tag(str, Enum):
    TAKE_PROFIT = 'take_profit'
    STOP_LOSS = 'stop_loss'
    ENTRY = 'entry'
    ORPHAN = 'orphan'
