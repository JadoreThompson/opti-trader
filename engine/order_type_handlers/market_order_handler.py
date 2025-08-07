from pprint import pprint
from engine.event_service import EventService
from enums import EventType, OrderStatus, OrderType, Side
from .order_type_handler import OrderTypeHandler
from ..enums import MatchOutcome, Tag
from ..matching_engines import Engine
from ..orders import SpotOrder
from ..order_context import OrderContext
from ..payloads import SpotPayload
from ..typing import MatchResult, OrderEnginePayloadData


class MarketOrderHandler(OrderTypeHandler):
    def can_handle(self, order_type: OrderType) -> bool:
        return order_type == OrderType.MARKET

    def handle_new(self, data: OrderEnginePayloadData, engine: Engine) -> None:
        db_payload = data.order
        payload = engine._create_payload(db_payload)
        context = engine._build_context(payload)
        order = engine._order_cls(
            id_=db_payload["order_id"],
            tag=Tag.ENTRY,
            side=db_payload["side"],
            quantity=db_payload["quantity"],
        )

        result: MatchResult = engine._execute_match(order, payload, context)
        pprint(db_payload)

        if result.outcome != MatchOutcome.SUCCESS:
            context.order_manager.append(order)
            order.price = (
                result.price
                if result.price is not None
                else (
                    db_payload["price"]
                    if db_payload["price"] is not None
                    else context.orderbook.price
                )
            )
            context.orderbook.append(order, order.price)
            EventService.log_order_event(
                EventType.ORDER_PLACED,
                db_payload,
                asset_balance=context.balance_manager.get_balance(
                    db_payload["user_id"]
                ),
            )

        return [db_payload]

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
