from pprint import pprint
from engine.event_service import EventService
from engine.protocols import PayloadProtocol
from enums import EventType, OrderStatus, OrderType, Side
from .order_type_handler import OrderTypeHandler
from ..enums import MatchOutcome, Tag
from ..matching_engines import Engine
from ..orders import Order
from ..order_context import OrderContext
from ..payloads import SpotPayload
from ..typing import MatchResult, OrderEnginePayloadData


class MarketOrderHandler(OrderTypeHandler):
    def can_handle(self, order_type: OrderType) -> bool:
        return order_type == OrderType.MARKET

    def handle_new(self, data: OrderEnginePayloadData, engine: Engine) -> None:
        db_payload = data.order
        payload = engine._create_payload(db_payload, OrderType.MARKET)
        context = engine._build_context(payload)
        order = Order(
            id_=db_payload["order_id"],
            typ=OrderType.MARKET,
            tag=Tag.ENTRY,
            side=db_payload["side"],
            quantity=db_payload["quantity"],
        )

        result: MatchResult = engine._execute_match(order, payload, context)

        if result.outcome != MatchOutcome.SUCCESS:
            context.order_store.add(order)
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
