from engine.event_service import EventService
from enums import EventType, OrderStatus, OrderType, Side
from .order_type_handler import OrderTypeHandler
from ..enums import MatchOutcome
from ..orders import SpotOrder
from ..order_context import OrderContext
from ..payloads import SpotPayload
from ..typing import MatchResult


class MarketOrderHandler(OrderTypeHandler):
    def can_handle(self, order_type: OrderType) -> bool:
        return order_type == OrderType.MARKET

    def handle(
        self, order: SpotOrder, payload: SpotPayload, context: OrderContext
    ) -> None:
        db_payload = payload.payload
        result: MatchResult = context.engine._execute_match(order, db_payload, context)

        if result.outcome != MatchOutcome.SUCCESS:
            order.price = (
                result.price if result.price is not None else db_payload["price"]
            )
            context.order_book.append(order, order.price)
            EventService.log_order_event(
                EventType.ORDER_PLACED,
                db_payload,
                asset_balance=context.balance_manager.get_balance(
                    db_payload["user_id"]
                ),
            )

    def handle_filled(
        self,
        quantity: int,
        price: float,
        order: SpotOrder,
        payload: SpotPayload,
        context: OrderContext,
    ) -> None:
        db_payload = payload.payload
        bm = context.balance_manager

        payload.apply_fill(quantity, price)

        if db_payload["side"] == Side.BID:
            bm.increase_balance(db_payload["user_id"], quantity)
        else:
            bm.decrease_balance(db_payload["user_id"], quantity)

        context.order_book.remove(order, order.price)
