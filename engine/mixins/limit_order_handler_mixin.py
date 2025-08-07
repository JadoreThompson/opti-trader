from typing import Any

from enums import EventType, Side
from ..enums import MatchOutcome, Tag
from ..event_service import EventService
from ..orderbook import OrderBook
from ..orders import Order, Order
from ..order_context import OrderContext
from ..typing import OrderEnginePayloadData, MatchResult

class LimitOrderHandlerMixin:
    def _is_crossable(self, order: Order, payload: dict, ob: OrderBook) -> bool:
        return (
            order.side == Side.BID
            and ob.best_ask is not None
            and payload["limit_price"] >= ob.best_ask
        ) or (
            order.side == Side.ASK
            and ob.best_bid is not None
            and payload["limit_price"] <= ob.best_bid
        )
