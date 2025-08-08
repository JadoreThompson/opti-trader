from enums import OrderType
from ..mixins import LimitOrderHandlerMixin, StopOrderHandlerMixin
from ..orderbook import OrderBook
from ..orders import Order


class OrderHandlerMixin:
    def _cancel_replace(self, order: Order, price: float, orderbook: OrderBook) -> bool:
        if order.type == OrderType.LIMIT and LimitOrderHandlerMixin._is_crossable(
            self, order, {"limit_price": price}, orderbook
        ):
            return False
        elif order.type == OrderType.STOP and StopOrderHandlerMixin._is_crossable(
            self, order, {"stop_price": price}, orderbook
        ):
            return False

        orderbook.remove(order, order.price)
        order.price = price
        orderbook.append(order, order.price)
        return True
