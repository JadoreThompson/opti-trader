from enums import EventType, OrderStatus, OrderType, Side
from .order_type_handler import OrderTypeHandler
from ..enums import MatchOutcome
from ..event_service import EventService
from ..mixins import LimitOrderHandlerMixin
from ..orders import SpotOrder
from ..order_context import OrderContext
from ..payloads import SpotPayload
from ..typing import MatchResult


class LimitOrderHandler(LimitOrderHandlerMixin, OrderTypeHandler):
    @staticmethod
    def is_modifiable():
        return True

    @staticmethod
    def is_cancellable():
        return False

    def can_handle(self, order_type: OrderType) -> bool:
        return order_type == OrderType.LIMIT

    def handle(
        self, order: SpotOrder, payload: SpotPayload, context: OrderContext
    ) -> None:
        ob = context.order_book
        db_payload = payload.payload

        # Check if crossable
        if self._is_crossable(order, db_payload, ob):
            result = context.engine._execute_match(order, payload, context)
            self._handle_match_result(result, order, payload, context)
        else:
            order.price = db_payload["limit_price"]
            ob.append(order, order.price)
            context.order_manager.append(order)
            EventService.log_order_event(
                EventType.ORDER_PLACED,
                db_payload,
                quantity=db_payload["quantity"],
                asset_balance=context.balance_manager.get_balance(
                    db_payload["user_id"]
                ),
            )

    def _handle_match_result(
        self,
        result: MatchResult,
        order: SpotOrder,
        payload: SpotPayload,
        context: OrderContext,
    ) -> None:
        if result.outcome != MatchOutcome.SUCCESS:
            db_payload = payload.payload
            order.price = (
                result.price if result.price is not None else db_payload["price"]
            )
            context.order_book.append(order, order.price)
            context.order_manager.append(order)
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
        payload: dict,
        context: OrderContext,
    ) -> None:
        context.order_manager.remove(order.id)
        # context.balance_manager.increase_balance(payload["user_id"], quantity)
