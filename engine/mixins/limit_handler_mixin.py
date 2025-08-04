from enums import Side
from ..orders import Order
from ..orderbook import OrderBook

class LimitOrderHandlerMixin:
    @staticmethod
    def _is_crossable(order: Order, payload: dict, ob: OrderBook) -> bool:
        return (
            order.side == Side.BID
            and ob.best_ask is not None
            and payload["limit_price"] >= ob.best_ask
        ) or (
            order.side == Side.ASK
            and ob.best_bid is not None
            and payload["limit_price"] <= ob.best_bid
        )