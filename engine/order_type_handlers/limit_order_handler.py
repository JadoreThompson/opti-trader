from enums import OrderStatus, OrderType
from .order_type_handler import OrderTypeHandler
from ..mixins import LimitOrderHandlerMixin
from ..orders import SpotOrder
from ..order_context import OrderContext


class LimitOrderHandler(LimitOrderHandlerMixin, OrderTypeHandler):
    @staticmethod
    def is_modifiable():
        return True

    @staticmethod
    def is_cancellable():
        return False

    def can_handle(self, order_type: OrderType) -> bool:
        return order_type == OrderType.LIMIT

    def handle(self, order: SpotOrder, payload: dict, context: OrderContext) -> None:
        ob = context.orderbook

        # Check if crossable
        if self._is_crossable(order, payload, ob):
            context.engine._execute_match(order, payload, context)
        else:
            order.price = payload["limit_price"]
            ob.append(order, order.price)
            context.order_manager.append(order)
            context.engine._log_order_new(
                payload,
                price=payload["limit_price"],
                quantity=payload["quantity"],
                asset_balance=context.balance_manager.get_balance(payload["user_id"]),
            )

    def handle_filled(
        self, quantity: int, order: SpotOrder, payload: dict, context: OrderContext
    ) -> None:
        payload["status"] = OrderStatus.FILLED
        context.order_manager.remove(order.id)
        context.balance_manager.increase_balance(payload["user_id"], quantity)

    def handle_touched(
        self, quantity: int, order: SpotOrder, payload: dict, context: OrderContext
    ) -> None:
        return super().handle_touched(order, payload, context)
