from enums import OrderStatus, OrderType
from .order_type_handler import OrderTypeHandler
from ..orders import SpotOrder
from ..order_context import OrderContext


class MarketOrderHandler(OrderTypeHandler):
    def can_handle(self, order_type: OrderType) -> bool:
        return order_type == OrderType.MARKET

    def handle(self, order: SpotOrder, payload: dict, context: OrderContext) -> None:
        ob = context.orderbook
        context.engine._execute_match(order, payload, context)

    def handle_filled(
        self, quantity: int, order: SpotOrder, payload: dict, context: OrderContext
    ) -> None:
        if payload['side']
        payload["status"] = OrderStatus.FILLED
        context.order_manager.remove(order.id)
        context.balance_manager.increase_balance(payload["user_id"], quantity)

    def handle_touched(
        self, order: SpotOrder, payload: dict, context: OrderContext
    ) -> None:
        return super().handle_touched(order, payload, context)
