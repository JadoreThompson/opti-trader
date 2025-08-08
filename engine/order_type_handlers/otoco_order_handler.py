from enums import EventType, OrderStatus, OrderType, Side
from .order_type_handler import OrderTypeHandler
from ..config import MODIFY_REQUEST_SENTINEL
from ..event_service import EventService
from ..enums import Tag
from ..mixins import LimitOrderHandlerMixin, StopOrderHandlerMixin
from ..orderbook import OrderBook
from ..order_context import OrderContext
from ..orders import OTOCOOrder
from ..protocols import EngineProtocol, PayloadProtocol
from ..typing import (
    LegModification,
    OTOCOEnginePayloadData,
    OTOCOModifyRequest,
)
from ..utils import get_price_key


class OTOCOOrderHandler(OrderTypeHandler):
    @staticmethod
    def is_modifiable() -> bool:
        return True

    def can_handle(self, order_type: OrderType) -> bool:
        return order_type == OrderType._OTOCO

    def handle_new(
        self, data: OTOCOEnginePayloadData, engine: EngineProtocol
    ) -> list[dict]:
        worker_db_payload = data.working_order
        trigger_payload = engine._create_payload(worker_db_payload, OrderType._OTOCO)
        price_key = get_price_key(worker_db_payload["order_type"])
        trigger_order = OTOCOOrder(
            id_=worker_db_payload["order_id"],
            typ=worker_db_payload["order_type"],
            tag=Tag.ENTRY,
            side=worker_db_payload["side"],
            quantity=worker_db_payload["quantity"],
            price=worker_db_payload[price_key],
            is_trigger=True,
        )

        above_tag = (
            Tag.TAKE_PROFIT if worker_db_payload["side"] == Side.BID else Tag.STOP_LOSS
        )
        below_tag = Tag.TAKE_PROFIT if above_tag == Tag.STOP_LOSS else Tag.STOP_LOSS

        above_db_payload = data.above_order
        engine._create_payload(above_db_payload, OrderType._OTOCO, validate=False)
        price_key = get_price_key(above_db_payload["order_type"])
        above_order = OTOCOOrder(
            id_=above_db_payload["order_id"],
            typ=above_db_payload["order_type"],
            tag=above_tag,
            side=above_db_payload["side"],
            quantity=above_db_payload["quantity"],
            price=above_db_payload[price_key],
            is_trigger=False,
            trigger_order=trigger_order,
        )

        below_db_payload = data.below_order
        engine._create_payload(below_db_payload, OrderType._OTOCO, validate=False)
        price_key = get_price_key(below_db_payload["order_type"])
        below_order = OTOCOOrder(
            id_=below_db_payload["order_id"],
            typ=below_db_payload["order_type"],
            tag=below_tag,
            side=below_db_payload["side"],
            quantity=below_db_payload["quantity"],
            price=below_db_payload[price_key],
            is_trigger=False,
            trigger_order=trigger_order,
        )

        trigger_order.above_order = above_order
        trigger_order.below_order = below_order

        context = engine._build_context(trigger_payload)
        context.orderbook.append(trigger_order, trigger_order.price)

        context.order_store.add(trigger_order)
        context.order_store.add(above_order)
        context.order_store.add(below_order)

        return []

    def handle_filled(
        self,
        quantity: int,
        price: float,
        order: OTOCOOrder,
        payload: PayloadProtocol,
        context: OrderContext,
    ) -> list[dict]:
        if order.filled_quantity != order.quantity:
            return []

        ob = context.orderbook
        ob.remove(order, order.price)

        if order.is_trigger:
            ob.append(order.above_order, order.above_order.price)
            ob.append(order.below_order, order.below_order.price)
            return []

        cparty = (
            order.trigger_order.above_order
            if order is order.trigger_order.below_order
            else order.trigger_order.below_order
        )
        cparty_payload = context.payload_store.get(cparty.id)

        ob.remove(cparty, cparty.price)

        order_store = context.order_store
        order_store.remove(order)
        order_store.remove(order.trigger_order)
        order_store.remove(cparty)

        payload_store = context.payload_store
        payload_store.remove(payload)
        payload_store.remove(context.payload_store.get(order.trigger_order.id))
        payload_store.remove(cparty_payload)

        cparty_payload.apply_cancel(cparty_payload.payload["standing_quantity"])
        return [payload.payload, cparty_payload.payload]

    def cancel(
        self,
        quantity: int,
        payload: PayloadProtocol,
        order: OTOCOOrder,
        context: OrderContext,
    ) -> list[dict]:
        above_order, below_order = order.above_order, order.below_order
        above_payload = context.payload_store.get(above_order.id)
        below_payload = context.payload_store.get(below_order.id)

        ob = context.orderbook
        order_store, payload_store = context.order_store, context.payload_store

        if order.is_trigger:
            ob.remove(order, order.price)
        else:
            trigger = order.trigger_order
            ob.remove(trigger.above_order, trigger.above_order.price)
            ob.remove(trigger.below_order, trigger.below_order.price)

        order_store.remove(order)
        order_store.remove(above_order)
        order_store.remove(below_order)

        payload_store.remove(payload)
        payload_store.remove(above_payload)
        payload_store.remove(below_payload)

        if payload.payload["status"] == OrderStatus.FILLED:
            ob.remove(above_order, above_order.price)
            ob.remove(below_order, below_order.price)

        payload.apply_cancel(quantity)
        above_payload.apply_cancel(above_payload.payload["standing_quantity"])
        below_payload.apply_cancel(below_payload.payload["standing_quantity"])

        return [payload.payload, above_payload.payload, below_payload.payload]

    def modify(
        self,
        request: OTOCOModifyRequest,
        payload: PayloadProtocol,
        order: OTOCOOrder,
        context: OrderContext,
    ) -> list[dict]:
        if order.is_trigger:
            trigger_order = order
            above_order = order.above_order
            below_order = order.below_order

            trigger_payload = payload
            above_payload = context.payload_store.get(above_order.id)
            below_payload = context.payload_store.get(below_order.id)
        else:
            trigger_order = order.trigger_order
            above_order = order.above_order
            below_order = order.below_order

            trigger_payload = context.payload_store.get(trigger_order.id)
            above_payload = (
                payload
                if order is above_order
                else context.payload_store.get(above_order.id)
            )
            below_payload = (
                payload
                if order is below_order
                else context.payload_store.get(below_order.id)
            )

        if not self._validate_modify(
            request,
            trigger_order,
            above_order,
            below_order,
            context.orderbook,
        ):
            return

        ob = context.orderbook
        bm = context.balance_manager

        ob.remove(trigger_order, trigger_order.price)
        if trigger_payload.payload['status'] == OrderStatus.FILLED:
            ob.remove(above_order, above_order.price)
            ob.remove(below_order, below_order.price)

        if request.trigger is not None:
            if request.trigger.limit_price != MODIFY_REQUEST_SENTINEL:
                trigger_order.price = request.trigger.limit_price
            if request.trigger.stop_price != MODIFY_REQUEST_SENTINEL:
                trigger_order.price = request.trigger.stop_price

        if request.above is not None:
            if request.above.limit_price != MODIFY_REQUEST_SENTINEL:
                above_order.price = request.above.limit_price
            if request.above.stop_price != MODIFY_REQUEST_SENTINEL:
                above_order.price = request.above.stop_price

        if request.below is not None:
            if request.below.limit_price != MODIFY_REQUEST_SENTINEL:
                below_order.price = request.below.limit_price
            if request.below.stop_price != MODIFY_REQUEST_SENTINEL:
                below_order.price = request.below.stop_price

        ob.append(trigger_order, trigger_order.price)
        if trigger_payload.payload['status'] == OrderStatus.FILLED:
            ob.append(above_order, above_order.price)
            ob.append(below_order, below_order.price)

        def update_payload(order_obj: OTOCOOrder, pl: PayloadProtocol):
            pk = "limit_price" if order_obj.type == OrderType.LIMIT else "stop_price"
            pl.payload[pk] = order_obj.price
            EventService.log_order_event(
                EventType.ORDER_MODIFIED,
                pl.payload,
                **{pk: order_obj.price},
                asset_balance=bm.get_balance(pl.payload),
            )

        update_payload(trigger_order, trigger_payload)
        update_payload(above_order, above_payload)
        update_payload(below_order, below_payload)

        return [
            trigger_payload.payload,
            above_payload.payload,
            below_payload.payload,
        ]

    def _validate_modify(
        self,
        request: OTOCOModifyRequest,
        trigger_order: OTOCOOrder,
        above_order: OTOCOOrder,
        below_order: OTOCOOrder,
        orderbook: OrderBook,
    ) -> bool:
        def evaluate(details: LegModification, order: OTOCOOrder) -> bool:
            nonlocal orderbook

            if (
                details.limit_price != MODIFY_REQUEST_SENTINEL
                and not LimitOrderHandlerMixin()._is_crossable(
                    order, {"limit_price": details.limit_price}, orderbook
                )
            ):
                return True
            elif (
                details.stop_price != MODIFY_REQUEST_SENTINEL
                and not StopOrderHandlerMixin()._is_crossable(
                    order, {"stop_price": details.stop_price}, orderbook
                )
            ):
                return True

            return False

        if request.trigger is not None and evaluate(request.trigger, trigger_order):
            return True

        if request.above is not None and evaluate(request.above, above_order):
            return True

        if request.below is not None and evaluate(request.below, below_order):
            return True

        return False
