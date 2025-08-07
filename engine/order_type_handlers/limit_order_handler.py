from pprint import pprint
from enums import EventType, OrderStatus, OrderType, Side
from .order_type_handler import OrderTypeHandler
from ..matching_engines import Engine
from ..enums import MatchOutcome
from ..event_service import EventService
from ..mixins import LimitMixin
from ..orders import SpotOrder
from ..order_context import OrderContext
from ..payloads import SpotPayload, PayloadProtocol
from ..typing import ModifyRequest, OrderEnginePayloadData, MatchResult


class LimitOrderHandler(LimitMixin, OrderTypeHandler):
    @staticmethod
    def is_modifiable():
        return True

    def can_handle(self, order_type: OrderType) -> bool:
        return order_type == OrderType.LIMIT

    def handle_new(self, data: OrderEnginePayloadData, engine: Engine) -> None:
        order, _, context, _ = self._handle_new_order(data, engine)
        context.order_manager.append(order)
        return [data.order]

    def handle_filled(
        self,
        quantity: int,
        price: float,
        order: SpotOrder,
        payload: SpotPayload,
        context: OrderContext,
    ) -> None:
        if order.filled_quantity == order.quantity:
            context.orderbook.remove(order, order.price)
            context.order_manager.remove(order.id)

    def modify(
        self, request: ModifyRequest, payload: PayloadProtocol, context: OrderContext
    ) -> None:
        ob = context.orderbook
        db_payload = payload.payload
        order = context.order_manager.get(db_payload["order_id"])
        if order is None:
            return

        if self._is_crossable(order, db_payload, ob):
            EventService.log_rejection(
                payload,
                asset_balance=context.balance_manager.get_balance(
                    db_payload["user_id"]
                ),
            )
            return

        db_payload["limit_price"] = request.limit_price
        ob.remove(order, order.price)
        order.price = request.limit_price
        ob.append(order, order.price)
