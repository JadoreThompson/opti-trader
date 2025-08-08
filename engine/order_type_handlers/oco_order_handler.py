from engine.config import MODIFY_REQUEST_SENTINEL
from enums import EventType, OrderStatus, OrderType
from .order_type_handler import OrderTypeHandler
from ..event_service import EventService
from ..enums import Tag
from ..mixins import LimitOrderHandlerMixin, StopOrderHandlerMixin
from ..orderbook import OrderBook
from ..order_context import OrderContext
from ..orders import Order, OCOOrder
from ..protocols import EngineProtocol, PayloadProtocol
from ..typing import OCOEnginePayloadData, OCOModifyRequest


class OCOOrderHandler(OrderTypeHandler):
    @staticmethod
    def is_modifiable() -> bool:
        return True

    @staticmethod
    def is_cancellable() -> bool:
        return True

    def can_handle(self, order_type: OrderType) -> bool:
        return order_type == OrderType._OCO

    def handle_new(
        self, data: OCOEnginePayloadData, engine: EngineProtocol
    ) -> list[dict]:
        db_payloads = data.orders
        gr_price = float("-inf")
        prices = []

        for p in db_payloads:
            ot = p["order_type"]
            price = None

            if ot == OrderType.LIMIT:
                price = p["limit_price"]
            elif ot == OrderType.STOP:
                price = p["stop_price"]
            elif ot == OrderType.MARKET:
                price = p["price"]

            gr_price = max(gr_price, price)
            prices.append(price)

        if price is None:
            return

        counterparty_a, counterparty_b = None, None
        context = None

        for i, dbp in enumerate(db_payloads):
            payload = engine._create_payload(dbp, OrderType._OCO)
            if i == 0:
                context = engine._build_context(payload)

            entry_price = prices[i]
            order = OCOOrder(
                id_=dbp["order_id"],
                tag=Tag.ENTRY,
                typ=dbp["order_type"],
                side=dbp["side"],
                quantity=dbp["quantity"],
                is_above=entry_price == gr_price,
            )
            order.price = entry_price
            context.orderbook.append(order, order.price)
            engine._add_to_store(order, OrderType._OCO)

            if i == 0:
                counterparty_a = order
            else:
                counterparty_b = order

        counterparty_a.counterparty = counterparty_b
        counterparty_b.counterparty = counterparty_a

        return db_payloads

    def handle_filled(
        self,
        quantity: int,
        price: float,
        order: OCOOrder,
        payload: PayloadProtocol,
        context: OrderContext,
    ) -> None:
        cparty_order = order.counterparty

        if order.filled_quantity == order.quantity:
            context.orderbook.remove(order, order.price)
            context.orderbook.remove(cparty_order, cparty_order.price)
            context.order_store.remove(order)
            context.order_store.remove(cparty_order)

            cparty_payload = context.payload_store.get(cparty_order.id)
            payload.payload["status"] = OrderStatus.FILLED

            if cparty_payload.payload["open_quantity"] == 0:
                cparty_payload.payload["status"] = OrderStatus.CANCELLED

    def cancel(
        self,
        quantity: int,
        payload: PayloadProtocol,
        order: OCOOrder,
        context: OrderContext,
    ) -> None:
        cparty_order = order.counterparty
        cparty_payload = context.payload_store.get(cparty_order.id)

        payload.apply_cancel(quantity)
        cparty_payload.apply_cancel(cparty_payload.payload["standing_quantity"])

        context.orderbook.remove(order, order.price)
        context.orderbook.remove(cparty_order, cparty_order.price)
        context.order_store.remove(order)
        context.order_store.remove(cparty_order)

        order.counterparty = None
        cparty_order.counterparty = None

        return [payload.payload, cparty_payload.payload]

    def modify(
        self,
        request: OCOModifyRequest,
        payload: PayloadProtocol,
        order: OCOOrder,
        context: OrderContext,
    ) -> None:
        bm = context.balance_manager
        db_payload = payload.payload

        cparty_order = order.counterparty
        cparty_payload = context.payload_store.get(order.counterparty.id)
        cparty_db_payload = cparty_payload.payload

        if not self._validate_modify(request, order, context):
            EventService.log_order_event(
                EventType.ORDER_MODIFY_REJECTED,
                payload.payload,
                asset_balance=context.balance_manager.get_balance(payload.payload),
            )
            return []

        order_price = order.price
        cparty_price = cparty_order.price

        o = order if order.is_above else cparty_order
        if request.above_price != MODIFY_REQUEST_SENTINEL:
            if o is order:
                order_price = request.above_price
            else:
                cparty_price = request.above_price

        o = order if not order.is_above else cparty_order
        if request.below_price != MODIFY_REQUEST_SENTINEL:
            if o is order:
                order_price = request.below_price
            else:
                cparty_price = request.below_price

        context.orderbook.remove(order, order.price)
        context.orderbook.remove(cparty_order, cparty_order.price)

        order.price = order_price
        cparty_order.price = cparty_price

        context.orderbook.append(order, order.price)
        context.orderbook.append(cparty_order, cparty_order.price)

        dbp_update = {}
        if db_payload["order_type"] == OrderType.LIMIT:
            dbp_update["limit_price"] = order_price
        else:
            dbp_update["stop_price"] = order_price
        db_payload.update(dbp_update)

        cpp_update = {}
        if cparty_db_payload["order_type"] == OrderType.LIMIT:
            cpp_update["limit_price"] = cparty_price
        else:
            cpp_update["stop_price"] = cparty_price
        cparty_db_payload.update(cpp_update)

        EventService.log_order_event(
            EventType.ORDER_MODIFIED,
            db_payload,
            **dbp_update,
            asset_balance=bm.get_balance(db_payload)
        )

        EventService.log_order_event(
            EventType.ORDER_MODIFIED,
            cparty_db_payload,
            **cpp_update,
            asset_balance=bm.get_balance(cparty_db_payload)
        )

        return [db_payload, cparty_db_payload]

    def _validate_modify(
        self, request: OCOModifyRequest, order: OCOOrder, context: OrderContext
    ):
        ob = context.orderbook
        cparty_order = order.counterparty

        above_order = order if order.is_above else cparty_order
        below_order = order if above_order is cparty_order else cparty_order

        above_price = above_order.price
        below_price = below_order.price

        if request.above_price != MODIFY_REQUEST_SENTINEL:
            if self._check_crosses_spread(request.above_price, above_order, ob):
                return False
            above_price = request.above_price

        if request.below_price != MODIFY_REQUEST_SENTINEL:
            if self._check_crosses_spread(request.below_price, below_order, ob):
                return False
            below_price = request.below_price

        if below_price >= above_price:
            return False

        return True

    def _check_crosses_spread(self, price: float, order: Order, ob: OrderBook) -> bool:
        if order.type == OrderType.LIMIT:
            return LimitOrderHandlerMixin()._is_crossable(
                order, {"limit_price": price}, ob
            )
        return StopOrderHandlerMixin()._is_crossable(order, {"stop_price": price}, ob)
