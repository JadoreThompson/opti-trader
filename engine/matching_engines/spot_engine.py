from collections import defaultdict
from enums import EventType, MarketType, OrderStatus, OrderType, Side
from .engine import Engine
from ..enums import MatchOutcome
from ..event_service import EventService
from ..managers import SpotBalanceManager, InstrumentManager
from ..orderbook import OrderBook
from ..orders import Order
from ..order_context import OrderContext
from ..order_type_handlers import (
    LimitOrderHandler,
    MarketOrderHandler,
    OrderTypeHandler,
    OCOOrderHandler,
    StopOrderHandler,
)
from ..protocols import StoreProtocol
from ..payloads import SpotPayload
from ..stores import OrderStore, PayloadStore
from ..typing import (
    CancelRequest,
    EnginePayload,
    MatchResult,
    ModifyRequest,
)
from ..validation_service import SpotValidationService


class SpotEngine(SpotValidationService, Engine):
    def __init__(
        self,
        loop=None,
        queue=None,
    ):
        super().__init__(loop=loop, queue=queue)

        self._instrument_manager = InstrumentManager()
        self._order_type_handlers: dict[OrderType, OrderTypeHandler] = {
            OrderType.LIMIT: LimitOrderHandler(),
            OrderType.MARKET: MarketOrderHandler(),
            OrderType.STOP: StopOrderHandler(),
            OrderType._OCO: OCOOrderHandler(),
        }
        self._order_stores: dict[OrderType, OrderStore] = defaultdict(OrderStore)
        self._payload_store = PayloadStore[SpotPayload]()

    def _build_context(self, payload: SpotPayload) -> OrderContext:
        db_payload = payload.payload
        ob, bm = self._instrument_manager.get(db_payload["instrument"], MarketType.SPOT)
        return OrderContext(
            engine=self,
            orderbook=ob,
            balance_manager=bm,
            payload_store=self._payload_store,
            order_store=self._order_stores[payload.internal_type],
        )

    def place_order(self, payload: EnginePayload) -> None:
        handler = self._order_type_handlers.get(payload.type)
        if handler and handler.can_handle(payload.type):
            payloads: list[dict] = handler.handle_new(payload.data, self)

            if payloads:
                _, bm = self._instrument_manager.get(payloads[0]["instrument"])
                map(lambda x: bm.append(x["user_id"]), payloads)
                map(self._push_order_payload, payloads)

    def modify_order(self, request: ModifyRequest) -> None:
        payload = self._payload_store.get(request.order_id)
        if payload is None:
            print(1)
            return

        db_payload = payload.payload
        ot = payload.internal_type

        handler = self._order_type_handlers[ot]
        if not handler.is_modifiable():
            print(2)
            return

        order = self._order_stores[ot].get(db_payload["order_id"])
        if order is None:
            print(3)
            return

        ob, bm = self._instrument_manager.get(db_payload["instrument"])
        context = OrderContext(
            orderbook=ob,
            engine=self,
            order_store=self._order_stores[ot],
            payload_store=self._payload_store,
            balance_manager=bm,
        )
        db_payloads = handler.modify(request.data, payload, order, context)

        map(self._push_order_payload, db_payloads)

    def cancel_order(self, request: CancelRequest) -> None:
        payload = self._payload_store.get(request.order_id)
        if payload is None:
            return

        ot = payload.internal_type
        db_payload = payload.payload
        ob, bm = self._instrument_manager.get(db_payload["instrument"])

        handler = self._order_type_handlers[ot]

        store = self._order_stores[ot]
        order = store.get(db_payload["order_id"])
        if order is None:
            return

        context = OrderContext(
            orderbook=ob,
            engine=self,
            order_store=self._order_stores[ot],
            payload_store=self._payload_store,
            balance_manager=bm,
        )
        handler.cancel(db_payload["standing_quantity"], payload, order, context)

        self._push_order_payload(db_payload)

    def _execute_match(
        self, order: Order, payload: SpotPayload, context: OrderContext
    ) -> MatchResult:
        done = False
        quantity = order.quantity
        filled_volume = 0.0
        filled_price = 0.0
        last_price = None

        while not done:
            result = self._match(order, context.orderbook, quantity)

            if result.outcome != MatchOutcome.FAILURE:
                quantity -= result.quantity
                filled_volume += result.price * result.quantity
                filled_price = filled_volume / (order.quantity - quantity)
                last_price = result.price

            if result.outcome != MatchOutcome.PARTIAL:
                done = True

        if quantity < order.quantity:
            if quantity == 0:
                outcome = MatchOutcome.SUCCESS
            else:
                outcome = MatchOutcome.PARTIAL

            context.orderbook.set_price(last_price)
            _, bm = self._instrument_manager.get(payload.payload["instrument"])
            self._handle_post_match(
                quantity=order.quantity - quantity,
                price=filled_price,
                order=order,
                payload=payload,
                balance_manager=bm,
                orderbook=context.orderbook,
            )

            self._push_order_payload(payload.payload)
        else:
            outcome = MatchOutcome.FAILURE

        return MatchResult(
            outcome=outcome, quantity=order.quantity - quantity, price=last_price
        )

    def _handle_post_match(
        self,
        quantity: int,
        price: float,
        order: Order,
        payload: SpotPayload,
        orderbook: OrderBook,
        balance_manager: SpotBalanceManager,
    ) -> None:
        db_payload = payload.payload

        orderbook.set_price(price)
        payload.apply_fill(quantity, price)
        order.filled_quantity += quantity

        if order.side == Side.BID:
            balance_manager.increase_balance(db_payload, quantity)
        else:
            balance_manager.decrease_balance(db_payload, quantity)

        event_type = (
            EventType.ORDER_FILLED
            if order.filled_quantity == order.quantity
            else EventType.ORDER_PARTIALLY_FILLED
        )

        EventService.log_order_event(
            event_type,
            db_payload,
            quantity=quantity,
            price=price,
            asset_balance=balance_manager.get_balance(db_payload),
            metadata={"tag": order.tag, "market_type": MarketType.SPOT},
        )

    def _handle_fill(
        self, order: Order, quantity: int, price: float, ob: OrderBook
    ) -> None:
        payload = self._payload_store.get(order.id)
        ot = payload.internal_type
        _, bm = self._instrument_manager.get(payload.payload["instrument"])

        self._handle_post_match(
            quantity=quantity,
            price=price,
            order=order,
            payload=payload,
            balance_manager=bm,
            orderbook=ob,
        )

        context = OrderContext(
            orderbook=ob,
            engine=self,
            balance_manager=bm,
            order_store=self._order_stores[ot],
            payload_store=self._payload_store,
        )

        handler = self._order_type_handlers[ot]
        handler.handle_filled(quantity, price, order, payload, context)
        self._push_order_payload(payload.payload)

    def _create_payload(
        self, db_payload: dict, internal_type: OrderType
    ) -> SpotPayload:
        if self._validate_new(db_payload):
            payload = SpotPayload(db_payload, internal_type)
            self._payload_store.add(payload)
            return payload
        raise ValueError("Invalid payload.")
    
    def _add_to_store(self, order: Order, internal_type: OrderType) -> None:
        self._order_stores[internal_type].add(order)
