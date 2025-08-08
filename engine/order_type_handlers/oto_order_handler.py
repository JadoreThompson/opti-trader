from enums import EventType, OrderStatus, OrderType
from .order_type_handler import OrderTypeHandler
from ..config import MODIFY_REQUEST_SENTINEL
from ..event_service import EventService
from ..enums import Tag
from ..mixins import LimitOrderHandlerMixin, StopOrderHandlerMixin
from ..orderbook import OrderBook
from ..order_context import OrderContext
from ..orders import Order, OTOOrder
from ..protocols import EngineProtocol, PayloadProtocol
from ..typing import (
    LegModification,
    OTOEnginePayloadData,
    OTOModifyRequest,
)
from ..utils import get_price_key


class OTOOrderHandler(LimitOrderHandlerMixin, StopOrderHandlerMixin, OrderTypeHandler):
    @staticmethod
    def is_modifiable() -> None:
        return True

    def can_handle(self, order_type: OrderType) -> bool:
        return order_type == OrderType._OTO

    def handle_new(
        self, data: OTOEnginePayloadData, engine: EngineProtocol
    ) -> list[dict]:
        working_db_payload = data.working_order
        pending_db_payload = data.pending_order

        working_payload = engine._create_payload(working_db_payload, OrderType._OTO)
        engine._create_payload(pending_db_payload, OrderType._OTO, validate=False)

        price_key = get_price_key(working_db_payload["order_type"])
        working_order = OTOOrder(
            id_=working_db_payload["order_id"],
            typ=working_db_payload["order_type"],
            tag=Tag.ENTRY,
            side=working_db_payload["side"],
            quantity=working_db_payload["quantity"],
            price=working_db_payload[price_key],
            is_worker=True,
        )

        price_key = get_price_key(pending_db_payload["order_type"])
        pending_order = OTOOrder(
            id_=pending_db_payload["order_id"],
            typ=pending_db_payload["order_type"],
            tag=Tag.ENTRY,
            side=pending_db_payload["side"],
            quantity=pending_db_payload["quantity"],
            price=pending_db_payload[price_key],
            is_worker=False,
        )
        working_order.counterparty = pending_order
        pending_order.counterparty = working_order

        context = engine._build_context(working_payload)
        context.orderbook.append(working_order, working_order.price)
        context.order_store.add(working_order)
        context.order_store.add(pending_order)

        return [working_db_payload, pending_db_payload]

    def handle_filled(self, quantity, price, order: OTOOrder, payload, context) -> None:
        if order.is_worker:
            self._handle_worker_filled(order, payload, context)
        else:
            self._handle_pending_filled(order.counterparty, order, context)

    def cancel(
        self, quantity: int, payload: PayloadProtocol, order: OTOOrder, context
    ) -> None:
        if order.is_worker:
            worker_order = order
            pending_order = order.counterparty
        else:
            worker_order = order.counterparty
            pending_order = order

        cid = order.counterparty.id

        if order.is_worker:
            pending_payload = context.payload_store.get(cid)
            worker_payload = payload
        else:
            worker_payload = context.payload_store.get(cid)
            pending_payload = payload

        if worker_payload.payload["status"] in (
            OrderStatus.PENDING,
            OrderStatus.PARTIALLY_FILLED,
        ):
            context.orderbook.remove(worker_order, worker_order.price)

        if worker_payload.payload["status"] == OrderStatus.FILLED:
            context.orderbook.remove(pending_order, pending_order.price)

        context.order_store.remove(worker_order)
        context.order_store.remove(pending_order)

        context.payload_store.remove(worker_payload)
        context.payload_store.remove(pending_payload)

        worker_payload.apply_cancel(worker_payload.payload["standing_quantity"])
        pending_payload.apply_cancel(pending_payload.payload["standing_quantity"])

        asset_balance = context.balance_manager.get_balance(payload.payload)

        EventService.log_order_event(
            EventType.ORDER_CANCELLED,
            worker_payload.payload,
            quantity=quantity,
            asset_balance=asset_balance,
        )
        EventService.log_order_event(
            EventType.ORDER_CANCELLED,
            pending_payload.payload,
            quantity=pending_payload.payload["standing_quantity"],
            asset_balance=asset_balance,
        )

        return [worker_payload.payload, pending_payload.payload]

    def modify(
        self,
        request: OTOModifyRequest,
        payload: PayloadProtocol,
        order: OTOOrder,
        context: OrderContext,
    ) -> None:
        cparty = order.counterparty

        if order.is_worker:
            worker_order = order
            pending_order = order.counterparty
        else:
            worker_order = order.counterparty
            pending_order = order

        worker_payload = context.payload_store.get(worker_order.id)
        pending_payload = context.payload_store.get(pending_order.id)

        new_working_price, working_price_key = None, None
        new_pending_price, pending_price_key = None, None

        if request.working is not None and worker_payload.payload["status"] in (
            OrderStatus.PENDING,
            OrderStatus.PARTIALLY_FILLED,
        ):
            details: LegModification = request.working

            if (
                details.limit_price != MODIFY_REQUEST_SENTINEL
                and worker_payload.payload["order_type"] == OrderType.LIMIT
            ):
                new_working_price, working_price_key = (
                    details.limit_price,
                    "limit_price",
                )
            if (
                details.stop_price != MODIFY_REQUEST_SENTINEL
                and worker_payload.payload["order_type"] == OrderType.STOP
            ):
                new_working_price, working_price_key = details.stop_price, "stop_price"

        elif request.pending is not None:
            details: LegModification = request.pending

            if (
                details.limit_price != MODIFY_REQUEST_SENTINEL
                and pending_payload.payload["order_type"] == OrderType.LIMIT
            ):
                new_pending_price, pending_price_key = (
                    details.limit_price,
                    "limit_price",
                )
            if (
                details.stop_price != MODIFY_REQUEST_SENTINEL
                and pending_payload.payload["order_type"] == OrderType.STOP
            ):
                new_pending_price, pending_price_key = details.stop_price, "stop_price"

        asset_bal = context.balance_manager.get_balance(worker_payload.payload)

        if new_working_price is not None and working_price_key is not None:
            if self._cancel_replace(worker_order, new_working_price, context.orderbook):

                worker_payload.payload[working_price_key] = new_working_price
            else:
                EventService.log_order_event(
                    EventType.ORDER_MODIFY_REJECTED,
                    worker_payload.payload,
                    asset_balance=asset_bal,
                )

        if new_pending_price is not None and pending_price_key is not None:
            persist = True
            if worker_payload.payload["status"] == OrderStatus.FILLED:
                persist = self._cancel_replace(
                    pending_order, new_pending_price, context.orderbook
                )

            if persist:
                pending_payload.payload[pending_price_key] = new_pending_price
            else:
                EventService.log_order_event(
                    EventType.ORDER_MODIFY_REJECTED,
                    pending_payload.payload,
                    asset_balance=asset_bal,
                )

        return [worker_payload.payload, pending_payload.payload]

    def _handle_worker_filled(
        self, order: OTOOrder, payload: PayloadProtocol, context: OrderContext
    ) -> None:
        if order.filled_quantity != order.quantity:
            return

        context.orderbook.remove(order, order.price)
        context.order_store.remove(order)

        pending_order = order.counterparty
        context.orderbook.append(pending_order, pending_order.price)

    def _handle_pending_filled(
        self, worker_order: OTOOrder, pending_order: OTOOrder, context: OrderContext
    ) -> None:
        if worker_order.filled_quantity != worker_order.quantity:
            return

        context.orderbook.remove(pending_order, pending_order.price)

        context.order_store.remove(worker_order)
        context.order_store.remove(pending_order)

        context.payload_store.remove(context.payload_store.get(worker_order.id))
        context.payload_store.remove(context.payload_store.get(pending_order.id))

    def _cancel_replace(self, order: Order, price: float, orderbook: OrderBook) -> bool:
        if order.type == OrderType.LIMIT and LimitOrderHandlerMixin._is_crossable(
            self, order, {"limit_price": price}, orderbook
        ):
            return False
        elif order.type == OrderType.STOP and StopOrderHandlerMixin._is_crossable(
            self, order, {"stop_price": price}, orderbook
        ):
            return False

        orderbook.remove(order, order.price)
        order.price = price
        orderbook.append(order, order.price)
        return True
