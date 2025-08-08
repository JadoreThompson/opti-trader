from enums import EventType, OrderType
from .order_type_handler import OrderTypeHandler
from ..matching_engines import Engine
from ..enums import MatchOutcome, Tag
from ..event_service import EventService
from ..orders import Order
from ..order_context import OrderContext
from ..payloads import SpotPayload
from ..protocols import PayloadProtocol
from ..typing import LimitModifyRequest, OrderEnginePayloadData, MatchResult


class LimitOrderHandler(OrderTypeHandler):
    @staticmethod
    def is_modifiable():
        return True

    def can_handle(self, order_type: OrderType) -> bool:
        return order_type == OrderType.LIMIT

    def handle_new(self, data: OrderEnginePayloadData, engine: Engine) -> None:
        db_payload = data.order
        payload = engine._create_payload(db_payload, OrderType.LIMIT)
        order = Order(
            id_=db_payload["order_id"],
            typ=OrderType.LIMIT,
            tag=Tag.ENTRY,
            side=db_payload["side"],
            quantity=db_payload["quantity"],
        )

        context = engine._build_context(payload)
        ob = context.orderbook

        if self._is_crossable(order, db_payload, ob):
            result: MatchResult = engine._execute_match(order, payload, context)
            if result.outcome == MatchOutcome.SUCCESS:
                return [db_payload]

        context.order_store.add(order)
        order.price = db_payload["limit_price"]
        ob.append(order, order.price)

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
        request: LimitModifyRequest,
        payload: PayloadProtocol,
        order: Order,
        context: OrderContext,
    ) -> None:
        ob = context.orderbook
        db_payload = payload.payload

        if self._is_crossable(order, db_payload, ob):
            EventService.log_rejection(
                payload,
                asset_balance=context.balance_manager.get_balance(
                    db_payload["user_id"]
                ),
            )
            return [db_payload]

        db_payload["limit_price"] = request.limit_price
        ob.remove(order, order.price)
        order.price = request.limit_price
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
