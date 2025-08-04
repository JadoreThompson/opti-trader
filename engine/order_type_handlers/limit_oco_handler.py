from engine.mixins.limit_handler_mixin import LimitOrderHandlerMixin
from engine.typing import ModifyRequest
from enums import OrderType
from .order_type_handler import OrderTypeHandler
from ..event_service import EventService
from ..mixins import LimitOrderHandlerMixin, ModifyTPSLMixin, OCOOrderHandlerMixin
from ..orders import SpotOrder
from ..order_context import OrderContext


class LimitOCOOrderHandler(
    OCOOrderHandlerMixin, LimitOrderHandlerMixin, ModifyTPSLMixin, OrderTypeHandler
):
    @staticmethod
    def is_modifiable() -> bool:
        return True

    def can_handle(self, order_type: OrderType) -> bool:
        return order_type == OrderType.LIMIT_OCO

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

    def handle_filled(self, quantity: int, order: SpotOrder, payload: dict, context: OrderContext) -> None:
        return super().handle_filled(order, payload, context)

    def handle_touched(self, quantity: int, order: SpotOrder, payload: dict, context: OrderContext) -> None:
        return super().handle_touched(order, payload, context)

    def modify(
        self,
        request: ModifyRequest,
        payload: dict,
        context: OrderContext,
    ) -> None:
        self._modify_tp_sl(request, payload, context)

    def cancel(
        self, quantity: int, payload: dict, order: SpotOrder, context: OrderContext
    ) -> None:
        self._cancel_order(quantity, payload, order, context)
