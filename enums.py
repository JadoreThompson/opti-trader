from enum import Enum


class MarketType(str, Enum):
    SPOT = "spot"
    FUTURES = "futures"


class Side(str, Enum):
    BID = "bid"
    ASK = "ask"


class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    STOP = 'stop'
    _OCO = 'oco'
    _OTO = 'oto'
    _OTOCO = 'otoco'


class OrderStatus(str, Enum):
    CANCELLED = "cancelled"
    PENDING = "pending"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    PARTIALLY_CLOSED = "partially_closed"
    CLOSED = "closed"


class EventType(str, Enum):
    # Order sent to the engine
    ASK_SUBMITTED = "ask_submitted"
    BID_SUBMITTED = "bid_submitted"

    # Order placed within orderbook
    ORDER_PLACED = "order_placed"

    ORDER_PARTIALLY_CANCELLED = "order_partially_cancelled"
    ORDER_CANCELLED = "order_cancelled"

    ORDER_MODIFIED = "order_modified"

    ORDER_PARTIALLY_FILLED = "order_partially_filled"
    ORDER_FILLED = "order_filled"

    ORDER_PARTIALLY_CLOSED = "order_partially_closed"
    ORDER_CLOSED = "order_closed"

    # Generic event when it doesn't fall under one of the others.
    ORDER_REJECTED = "order_rejected"

    # A new order sent to engine was rejected
    ORDER_NEW_REJECTED = "order_new_rejected"

    # A cancel request sent to the engine was rejected
    ORDER_CANCEL_REJECTED = "order_cancel_rejected"

    # # A modify request sent to the engine was rejected
    ORDER_MODIFY_REJECTED = "order_modify_rejected"


class ClientEventType(Enum):
    """
    Extra event types that may be emitted by listeners
    of the matching engies. i.e. PAYLOAD_UPDATE by
    the PayloadPusher
    """

    PAYLOAD_UPDATE = "payload_update"


class InstrumentEventType(Enum):
    PRICE_UPDATE = "price_update"
    ORDERBOOK_UPDATE = "orderbook_update"
    RECENT_TRADE = "recent_trade"
