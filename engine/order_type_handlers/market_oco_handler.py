from engine.typing import ModifyRequest
from enums import OrderType, Side
from .order_type_handler import OrderTypeHandler
from ..mixins import OCOOrderHandlerMixin, ModifyTPSLMixin
from ..event_service import EventService
from ..orders import SpotOrder, OCOOrder
from ..order_context import OrderContext


class MarketOCOOrderHandler(OCOOrderHandlerMixin, ModifyTPSLMixin, OrderTypeHandler):
    @staticmethod
    def is_modifiable() -> bool:
        return True

    def can_handle(self, order_type: OrderType) -> bool:
        return order_type == OrderType.MARKET_OCO

    def handle(self, order: SpotOrder, payload: dict, context: OrderContext):
        oco_order: OCOOrder = context.oco_manager.create()
        order.set_oco_id(oco_order.id)
        oco_order.leg_a = order

        context.order_manager.append(order)
        result = context.engine._execute_match(order, payload, context)
        self._handle_match_outcome(result.outcome)

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
