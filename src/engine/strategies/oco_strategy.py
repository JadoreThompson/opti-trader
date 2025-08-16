from json import dumps

from enums import EventType, StrategyType
from ..event_logger import EventLogger
from ..execution_context import ExecutionContext
from ..mixins import ModifyOrderMixin
from ..models import ModifyOrderCommand, NewOCOOrder
from ..orders import OCOOrder
from ..protocols import StrategyProtocol
from ..utils import get_price_key


class OCOStrategy(ModifyOrderMixin, StrategyProtocol):
    def handle_new(self, details: NewOCOOrder, ctx: ExecutionContext):
        leg_a, leg_b = details.legs

        order_a = OCOOrder(
            id_=leg_a["order_id"],
            user_id=leg_a["user_id"],
            strategy_type=StrategyType.OCO,
            side=leg_a["side"],
            order_type=leg_a["order_type"],
            quantity=leg_a["quantity"],
            price=leg_a[get_price_key(leg_a["order_type"])],
        )

        order_b = OCOOrder(
            id_=leg_b["order_id"],
            user_id=leg_b["user_id"],
            strategy_type=StrategyType.OCO,
            side=leg_b["side"],
            order_type=leg_b["order_type"],
            quantity=leg_b["quantity"],
            price=leg_b[get_price_key(leg_b["order_type"])],
        )

        order_a.counterparty = order_b
        order_b.counterparty = order_a

        ctx.orderbook.append(order_a, order_a.price)
        ctx.orderbook.append(order_b, order_b.price)
        ctx.order_store.add(order_a)
        ctx.order_store.add(order_b)

        EventLogger.log_event(
            EventType.ORDER_PLACED,
            user_id=order_a.user_id,
            related_id=order_a.id,
            instrument_id=ctx.instrument_id,
            details={
                "executed_quantity": order_a.executed_quantity,
                "quantity": order_a.quantity,
                "price": order_a.price,
                "side": order_a.side,
            },
        )
        EventLogger.log_event(
            EventType.ORDER_PLACED,
            user_id=order_b.user_id,
            related_id=order_b.id,
            instrument_id=ctx.instrument_id,
            details={
                "executed_quantity": order_b.executed_quantity,
                "quantity": order_b.quantity,
                "price": order_b.price,
                "side": order_b.side,
            },
        )

    def handle_filled(
        self, quantity: int, price: float, order: OCOOrder, ctx: ExecutionContext
    ) -> None:
        if order.executed_quantity != order.quantity:
            return

        self._cancel(order, ctx)
        EventLogger.log_event(
            EventType.ORDER_CANCELLED,
            user_id=order.user_id,
            related_id=order.counterparty.id,
            instrument_id=ctx.instrument_id,
            details=dumps({"reason": f"OCO peer {order.id} was filled."}),
        )

    def cancel(self, order: OCOOrder, ctx: ExecutionContext) -> None:
        self._cancel(order, ctx)
        EventLogger.log_event(
            EventType.ORDER_CANCELLED,
            user_id=order.user_id,
            related_id=order.id,
            instrument_id=ctx.instrument_id,
            details=dumps({"reason": "Client requested cancel."}),
        )
        EventLogger.log_event(
            EventType.ORDER_CANCELLED,
            user_id=order.user_id,
            related_id=order.counterparty.id,
            instrument_id=ctx.instrument_id,
            details=dumps({"reason": "Client requested cancel."}),
        )

    def _cancel(self, order: OCOOrder, ctx: ExecutionContext) -> None:
        ctx.orderbook.remove(order, order.price)
        ctx.orderbook.remove(order.counterparty, order.counterparty.price)
        ctx.order_store.remove(order)
        ctx.order_store.remove(order.counterparty)

    def modify(
        self, details: ModifyOrderCommand, order: OCOOrder, ctx: ExecutionContext
    ) -> None:
        self._modify_order(details, order, ctx)
