from json import dumps
from enums import EventType, OrderType, StrategyType
from ..enums import MatchOutcome
from ..event_logger import EventLogger
from ..execution_context import ExecutionContext
from ..mixins import ModifyOrderMixin
from ..models import ModifyOrderCommand, NewOTOOrder
from ..orders import OTOOrder
from ..protocols import StrategyProtocol
from ..typing import MatchResult
from ..utils import get_price_key, limit_crossable, stop_crossable


class OTOStrategy(ModifyOrderMixin, StrategyProtocol):
    def handle_new(self, details: NewOTOOrder, ctx: ExecutionContext):
        parent_data = details.parent
        child_data = details.child

        parent = OTOOrder(
            id_=parent_data["order_id"],
            user_id=parent_data["user_id"],
            strategy_type=StrategyType.OTO,
            order_type=parent_data["order_type"],
            side=parent_data["side"],
            quantity=parent_data["quantity"],
            price=parent_data[get_price_key(parent_data["order_type"])],
        )

        child = OTOOrder(
            id_=child_data["order_id"],
            user_id=child_data["user_id"],
            strategy_type=StrategyType.OTO,
            order_type=child_data["order_type"],
            side=child_data["side"],
            quantity=child_data["quantity"],
            price=child_data[get_price_key(child_data["order_type"])],
            parent=parent,
        )

        parent.child = child
        child.parent = parent

        matchable = True
        if parent_data["order_type"] == OrderType.LIMIT:
            matchable = limit_crossable(
                parent_data["limit_price"], parent.side, ctx.orderbook
            )
        if parent_data["order_type"] == OrderType.STOP:
            matchable = stop_crossable(
                parent_data["stop_price"], parent.side, ctx.orderbook
            )

        if matchable:
            result: MatchResult = ctx.engine.match(parent, ctx)
            parent.executed_quantity = result.quantity

            if result.outcome == MatchOutcome.UNAUTHORISED:
                return

            if result.outcome == MatchOutcome.SUCCESS:
                ctx.orderbook.append(child, child.price)
                ctx.order_store.add(child)
                EventLogger.log_event(
                    EventType.ORDER_PLACED,
                    user_id=child.user_id,
                    related_id=child.id,
                    instrument_id=ctx.instrument_id,
                    details={
                        "executed_quantity": child.executed_quantity,
                        "quantity": child.quantity,
                        "price": child.price,
                        "side": child.side,
                    },
                )
                return

        ctx.orderbook.append(parent, parent.price)
        ctx.order_store.add(parent)
        ctx.order_store.add(child)
        EventLogger.log_event(
            EventType.ORDER_PLACED,
            user_id=parent.user_id,
            related_id=parent.id,
            instrument_id=ctx.instrument_id,
            details={
                "executed_quantity": parent.executed_quantity,
                "quantity": parent.quantity,
                "price": parent.price,
                "side": parent.side,
            },
        )

    def handle_filled(
        self, quantity: int, price: float, order: OTOOrder, ctx: ExecutionContext
    ) -> None:
        # Parent
        if order.child and order.executed_quantity == order.quantity:
            child = order.child
            child.triggered = True
            ctx.orderbook.append(child, child.price)
            ctx.order_store.remove(order)
            EventLogger.log_event(
                EventType.ORDER_PLACED,
                user_id=child.user_id,
                related_id=child.id,
                instrument_id=ctx.instrument_id,
                details={
                    "executed_quantity": child.executed_quantity,
                    "quantity": child.quantity,
                    "price": child.price,
                    "side": child.side,
                },
            )
        elif order.executed_quantity == order.quantity:  # Child
            ctx.orderbook.remove(order, order.price)
            ctx.order_store.remove(order)

    def cancel(self, order: OTOOrder, ctx: ExecutionContext) -> None:
        if order.child:
            ctx.orderbook.remove(order, order.price)
            ctx.order_store.remove(order.child)

            EventLogger.log_event(
                EventType.ORDER_CANCELLED,
                user_id=order.user_id,
                related_id=order.id,
                instrument_id=ctx.instrument_id,
            )
            EventLogger.log_event(
                EventType.ORDER_CANCELLED,
                user_id=order.child.user_id,
                related_id=order.child.id,
                instrument_id=ctx.instrument_id,
                details=dumps({"reason": "Parent order cancelled."}),
            )
        elif order.parent:
            if order.triggered:
                ctx.orderbook.remove(order, order.price)
                EventLogger.log_event(
                    EventType.ORDER_CANCELLED,
                    user_id=order.user_id,
                    related_id=order.id,
                    instrument_id=ctx.instrument_id,
                )
            else:
                parent = order.parent
                ctx.orderbook.remove(parent, parent.price)
                ctx.order_store.remove(parent)
                EventLogger.log_event(
                    EventType.ORDER_CANCELLED,
                    user_id=parent.user_id,
                    related_id=parent.id,
                    instrument_id=ctx.instrument_id,
                )
                EventLogger.log_event(
                    EventType.ORDER_CANCELLED,
                    user_id=order.user_id,
                    related_id=order.id,
                    instrument_id=ctx.instrument_id,
                    details=dumps({"reason": "Parent order cancelled."}),
                )

        ctx.order_store.remove(order)

    def modify(
        self, details: ModifyOrderCommand, order: OTOOrder, ctx: ExecutionContext
    ):
        if order.parent:
            if order.triggered:
                self._modify_order(details, order, ctx)
            elif self._validate_modify(details, order, ctx):
                order.price = self._get_modified_price(details, order)
                EventLogger.log_event(
                    EventType.ORDER_MODIFIED,
                    user_id=order.user_id,
                    related_id=order.id,
                    instrument_id=ctx.instrument_id,
                    details=dumps({"price": order.price}),
                )
            return

        self._modify_order(details, order, ctx)
