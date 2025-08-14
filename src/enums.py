from enum import Enum


class Side(Enum):
    BID = "bid"
    ASK = "ask"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class TimeInForce(Enum):
    GTC = "GTC"  # Good Till Cancelled
    IOC = "IOC"  # Immediate Or Cancel
    FOK = "FOK"  # Fill Or Kill


class StrategyType(Enum):
    SINGLE = "SINGLE"
    OCO = "OCO"
    OTO = "OTO"
    OTOCO = "OTOCO"


class LiquidityRole(Enum):
    MAKER = "MAKER"
    TAKER = "TAKER"


class EventType(Enum):
    ORDER_PLACED = "order_placed"
    ORDER_PARTIALLY_FILLED = "order_partially_filled"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_MODIFIED = "order_modified"
    ORDER_MODIFY_REJECTED = "order_modify_rejected"
    NEW_TRADE = "new_trade"


class InstrumentEventType(Enum):
    PRICE = "price"
    TRADES = "trades"
    ORDERBOOK = "orderbook"


class TransactionType(Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRADE = "TRADE"
    ESCROW = "ESCROW"


class OrderStatus(Enum):
    PENDING = "pending"
    PLACED = 'placed'
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"


class UserStatus(Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


class InstrumentStatus(Enum):
    TRADABLE = "TRADABLE"
    DELISTED = "DELISTED"


class TimeFrame(Enum):
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
