from json import dumps
from enums import EventType, OrderType, StrategyType
from ..enums import MatchOutcome
from ..event_logger import EventLogger
from ..execution_context import ExecutionContext
from ..protocols import StrategyProtocol
from ..mixins import ModifyOrderMixin
from ..models import NewOTOCOOrder
from ..orders import OTOCOOrder
from ..typing import MatchResult
from ..utils import get_price_key, limit_crossable, stop_crossable


class OTOCOStrategy(ModifyOrderMixin, StrategyProtocol):
    def handle_new(self, details: NewOTOCOOrder, ctx: ExecutionContext) -> None:
        parent_data = details.parent
        child_leg_a_data, child_leg_b_data = details.oco_legs

        parent_order = OTOCOOrder(
            id_=parent_data["order_id"],
            user_id=parent_data["user_id"],
            strategy_type=StrategyType.OTOCO,
            order_type=parent_data["order_type"],
            side=parent_data["side"],
            quantity=parent_data["quantity"],
            price=parent_data[get_price_key(parent_data["order_type"])],
        )

        child_a = OTOCOOrder(
            id_=child_leg_a_data["order_id"],
            user_id=child_leg_a_data["user_id"],
            strategy_type=StrategyType.OTOCO,
            order_type=child_leg_a_data["order_type"],
            side=child_leg_a_data["side"],
            quantity=child_leg_a_data["quantity"],
            price=child_leg_a_data[get_price_key(child_leg_a_data["order_type"])],
            parent=parent_order,
        )

        child_b = OTOCOOrder(
            id_=child_leg_b_data["order_id"],
            user_id=child_leg_b_data["user_id"],
            strategy_type=StrategyType.OTOCO,
            order_type=child_leg_b_data["order_type"],
            side=child_leg_b_data["side"],
            quantity=child_leg_b_data["quantity"],
            price=child_leg_b_data[get_price_key(child_leg_b_data["order_type"])],
            parent=parent_order,
        )

        parent_order.child_a = child_a
        parent_order.child_b = child_b
        child_a.counterparty = child_b
        child_b.counterparty = child_a

        ctx.order_store.add(parent_order)
        ctx.order_store.add(child_a)
        ctx.order_store.add(child_b)

        matchable = True
        if parent_data["order_type"] == OrderType.LIMIT:
            matchable = limit_crossable(
                parent_data["limit_price"], parent_order.side, ctx.orderbook
            )
        if parent_data["order_type"] == OrderType.STOP:
            matchable = stop_crossable(
                parent_data["stop_price"], parent_order.side, ctx.orderbook
            )

        if matchable:
            result: MatchResult = ctx.engine.match(parent_order, ctx)
            parent_order.executed_quantity = result.quantity

            if result.outcome == MatchOutcome.UNAUTHORISED:
                return

            if result.outcome == MatchOutcome.SUCCESS:
                ctx.order_store.remove(parent_order)
                ctx.orderbook.append(child_a, child_a.price)
                ctx.orderbook.append(child_b, child_b.price)
                EventLogger.log_event(
                    EventType.ORDER_PLACED,
                    user_id=child_a.user_id,
                    related_id=child_a.id,
                    instrument_id=ctx.instrument_id,
                    details={
                        "executed_quantity": child_a.executed_quantity,
                        "quantity": child_a.quantity,
                        "price": child_a.price,
                        "side": child_a.side,
                    },
                )
                EventLogger.log_event(
                    EventType.ORDER_PLACED,
                    user_id=child_b.user_id,
                    related_id=child_b.id,
                    instrument_id=ctx.instrument_id,
                    details={
                        "executed_quantity": child_b.executed_quantity,
                        "quantity": child_b.quantity,
                        "price": child_b.price,
                        "side": child_b.side,
                    },
                )
                return

        ctx.orderbook.append(parent_order, parent_order.price)
        EventLogger.log_event(
            EventType.ORDER_PLACED,
            user_id=parent_order.user_id,
            related_id=parent_order.id,
            instrument_id=ctx.instrument_id,
            details={
                "executed_quantity": parent_order.executed_quantity,
                "quantity": parent_order.quantity,
                "price": parent_order.price,
                "side": parent_order.side,
            },
        )

    def handle_filled(
        self, quantity: int, price: float, order: OTOCOOrder, ctx: ExecutionContext
    ) -> None:
        # If the parent is filled, trigger the OCO children
        if order.child_a and order.executed_quantity == order.quantity:
            order.triggered = False  # Set to false for .cancel logic
            child = order.child_a
            child.triggered = True
            ctx.orderbook.append(child, child.price)
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

            child = order.child_b
            child.triggered = True
            ctx.orderbook.append(child, child.price)
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

            ctx.order_store.remove(order)
            return

        # If a child is filled, cancel its counterparty
        if order.counterparty and order.executed_quantity == order.quantity:
            counterparty = order.counterparty
            ctx.orderbook.remove(counterparty, counterparty.price)
            ctx.order_store.remove(order)
            ctx.order_store.remove(counterparty)
            EventLogger.log_event(
                EventType.ORDER_CANCELLED,
                user_id=counterparty.user_id,
                related_id=counterparty.id,
                instrument_id=ctx.instrument_id,
                details=dumps({"reason": f"OCO peer {order.id} was filled."}),
            )

    def cancel(self, order: OTOCOOrder, ctx: ExecutionContext) -> None:
        if order.child_a:  # Must beparent
            ctx.orderbook.remove(order, order.price)
            ctx.order_store.remove(order)
            ctx.order_store.remove(order.child_a)
            ctx.order_store.remove(order.child_b)
            EventLogger.log_event(
                EventType.ORDER_CANCELLED,
                user_id=order.user_id,
                related_id=order.id,
                instrument_id=ctx.instrument_id,
            )
            EventLogger.log_event(
                EventType.ORDER_CANCELLED,
                user_id=order.child_a.user_id,
                related_id=order.child_a.id,
                instrument_id=ctx.instrument_id,
                details=dumps({"reason": "Parent order cancelled."}),
            )
            EventLogger.log_event(
                EventType.ORDER_CANCELLED,
                user_id=order.child_b.user_id,
                related_id=order.child_b.id,
                instrument_id=ctx.instrument_id,
                details=dumps({"reason": "Parent order cancelled."}),
            )
            return

        # Must be child
        if order.parent.triggered:
            ctx.order_store.remove(order.parent)
        ctx.order_store.remove(order)
        ctx.order_store.remove(order.counterparty)

        if order.triggered:
            counterparty = order.counterparty
            ctx.orderbook.remove(order, order.price)
            ctx.orderbook.remove(counterparty, counterparty.price)
        else:
            ctx.orderbook.remove(order.parent, order.parent.price)

        if order.parent.triggered:
            EventLogger.log_event(
                EventType.ORDER_CANCELLED, user_id=order.user_id, related_id=order.id
            )

        EventLogger.log_event(
            EventType.ORDER_CANCELLED,
            user_id=order.user_id,
            related_id=order.id,
            instrument_id=ctx.instrument_id,
        )
        EventLogger.log_event(
            EventType.ORDER_CANCELLED,
            user_id=counterparty.user_id,
            related_id=counterparty.id,
            instrument_id=ctx.instrument_id,
        )

    def modify(self, details, order: OTOCOOrder, ctx: ExecutionContext):
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
