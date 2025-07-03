from enum import Enum


class MarketType(str, Enum):
    SPOT = "spot"
    FUTURES = "futures"


class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"


class Side(str, Enum):
    BID = "bid"
    ASK = "ask"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CLOSED = "closed"
    PARTIALLY_CLOSED = "partially_closed"
