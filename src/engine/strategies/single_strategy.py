from enums import EventType, OrderType, StrategyType
from ..enums import MatchOutcome
from ..event_logger import EventLogger
from ..execution_context import ExecutionContext
from ..mixins import ModifyOrderMixin
from ..models import NewSingleOrder
from ..orders import Order
from ..protocols import StrategyProtocol
from ..typing import MatchResult
from ..utils import get_price_key, limit_crossable, stop_crossable


class SingleOrderStrategy(ModifyOrderMixin, StrategyProtocol):
    def handle_new(self, details: NewSingleOrder, ctx: ExecutionContext):
        order_data = details.order
        order = Order(
            id_=order_data["order_id"],
            user_id=order_data["user_id"],
            strategy_type=StrategyType.SINGLE,
            order_type=order_data["order_type"],
            side=order_data["side"],
            quantity=order_data["quantity"],
            price=order_data[get_price_key(order_data["order_type"])],
        )

        matchable = True
        if order_data["order_type"] == OrderType.LIMIT:
            matchable = limit_crossable(
                order_data["limit_price"], order.side, ctx.orderbook
            )
        if order_data["order_type"] == OrderType.STOP:
            matchable = stop_crossable(
                order_data["stop_price"], order.side, ctx.orderbook
            )

        if matchable:
            result: MatchResult = ctx.engine.match(order, ctx)
            order.executed_quantity = result.quantity

            if result.outcome == MatchOutcome.UNAUTHORISED:
                EventLogger.log_event(
                    EventType.ORDER_CANCELLED,
                    user_id=order.user_id,
                    related_id=order.id,
                    instrument_id=ctx.instrument_id,
                    details={"reason": "Insufficient funds"},
                )
                return

            if result.outcome == MatchOutcome.SUCCESS:
                return

        ctx.order_store.add(order)
        ctx.orderbook.append(order, order.price)

        EventLogger.log_event(
            EventType.ORDER_PLACED,
            user_id=order.user_id,
            related_id=order.id,
            instrument_id=ctx.instrument_id,
            details={'executed_quantity': order.executed_quantity, "quantity": order.quantity, "price": order.price, "side": order.side}
        )

    def handle_filled(
        self, quantity: int, price: float, order: Order, ctx: ExecutionContext
    ) -> None:
        if order.executed_quantity == order.quantity:
            ctx.order_store.remove(order)

    def cancel(self, order: Order, ctx: ExecutionContext) -> None:
        ctx.orderbook.remove(order, order.price)
        ctx.order_store.remove(order)
        EventLogger.log_event(
            EventType.ORDER_CANCELLED,
            user_id=order.user_id,
            related_id=order.id,
            instrument_id=ctx.instrument_id,
            details={"reason": "Insufficient funds"},
        )

    def modify(self, details, order: Order, ctx: ExecutionContext):
        self._modify_order(details, order, ctx)
