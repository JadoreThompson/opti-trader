from enums import EventType, OrderType
from .order_type_handler import OrderTypeHandler
from ..enums import MatchOutcome, Tag
from ..event_service import EventService
from ..matching_engines import Engine
from ..mixins import StopOrderHandlerMixin
from ..order_context import OrderContext
from ..orders import Order
from ..payloads import SpotPayload
from ..protocols import PayloadProtocol
from ..typing import OrderEnginePayloadData, StopModifyRequest


class StopOrderHandler(StopOrderHandlerMixin, OrderTypeHandler):
    @staticmethod
    def is_modifiable() -> bool:
        return True

    def can_handle(self, order_type: OrderType) -> bool:
        return order_type == OrderType.STOP

    def handle_new(self, data: OrderEnginePayloadData, engine: Engine) -> None:
        db_payload = data.order
        payload = engine._create_payload(db_payload, OrderType.STOP)
        context = engine._build_context(payload)
        order = Order(
            id_=db_payload["order_id"],
            tag=Tag.ENTRY,
            typ=OrderType.STOP,
            side=db_payload["side"],
            quantity=db_payload["quantity"],
        )

        if self._is_crossable(order, db_payload, context.orderbook):
            result = engine._execute_match(order, payload, context)

            if result.outcome == MatchOutcome.SUCCESS:
                return [db_payload]

        context.order_store.add(order)
        order.price = db_payload["stop_price"]
        context.orderbook.append(order, order.price)
        EventService.log_order_event(
            EventType.ORDER_PLACED,
            db_payload,
            quantity=db_payload["quantity"],
            asset_balance=context.balance_manager.get_balance(db_payload),
        )

        return [db_payload]

    def handle_filled(
        self,
        quantity: int,
        price: float,
        order: Order,
        payload: SpotPayload,
        context: OrderContext,
    ) -> None:
        if order.filled_quantity == order.quantity:
            context.orderbook.remove(order, order.price)
            context.order_store.remove(order)

    def modify(
        self,
        request: StopModifyRequest,
        payload: PayloadProtocol,
        order: Order,
        context: OrderContext,
    ) -> list[dict]:
        ob = context.orderbook
        db_payload = payload.payload

        if self._is_crossable(order, db_payload, ob):
            EventService.log_rejection(
                payload,
                asset_balance=context.balance_manager.get_balance(db_payload),
            )
            return

        db_payload["stop_price"] = request.stop_price
        ob.remove(order, order.price)
        order.price = request.stop_price
        ob.append(order, order.price)
        return [db_payload]

    def cancel(
        self,
        quantity: int,
        payload: PayloadProtocol,
        order: Order,
        context: OrderContext,
    ):
        payload.apply_cancel(quantity)
        context.orderbook.remove(order, order.price)
        context.order_store.remove(order)
        return [payload.payload]
