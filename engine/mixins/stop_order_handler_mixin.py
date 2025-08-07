from ..orderbook import OrderBook
from ..orders import Order
from enums import Side


class StopOrderHandlerMixin:
    @staticmethod
    def _is_crossable(order: Order, payload: dict, ob: OrderBook) -> bool:
        return (
            order.side == Side.BID
            and ob.best_ask is not None
            and payload["stop_price"] <= ob.best_ask
        ) or (
            order.side == Side.ASK
            and ob.best_bid is not None
            and payload["stop_price"] >= ob.best_bid
        )
