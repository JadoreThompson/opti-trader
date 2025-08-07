from enums import EventType, MarketType, OrderStatus, OrderType, Side
from .engine import Engine
from ..enums import MatchOutcome, Tag
from ..event_service import EventService
from ..managers import BalanceManager
from ..managers import InstrumentManager
from ..managers import OrderManager
from ..orderbook.orderbook import OrderBook
from ..orders import SpotOrder
from ..order_context import OrderContext
from ..order_type_handlers import (
    LimitOrderHandler,
    MarketOrderHandler,
    OrderTypeHandler,
    StopOrderHandler,
)
from ..payloads import SpotPayload
from ..typing import (
    CancelRequest,
    EnginePayload,
    EnginePayloadData,
    MatchResult,
    ModifyRequest,
)
from ..validation_service import SpotValidationService


class SpotEngine(SpotValidationService, Engine[SpotOrder]):
    def __init__(
        self,
        loop=None,
        queue=None,
        payload_cls=None,
        order_cls=None,
        instrument_manager: InstrumentManager | None = None,
        order_manager: OrderManager | None = None,
    ):
        super().__init__(loop=loop, queue=queue)

        self._instrument_manager = instrument_manager or InstrumentManager()
        self._order_type_handlers: dict[OrderType, OrderTypeHandler] = {
            OrderType.LIMIT: LimitOrderHandler(),
            OrderType.MARKET: MarketOrderHandler(),
            OrderType.STOP: StopOrderHandler(),
        }
        self._order_manager = order_manager or OrderManager()
        self._payload_cls = payload_cls or SpotPayload
        self._order_cls = order_cls or SpotOrder

    def _build_context(self, payload: SpotPayload) -> OrderContext:
        db_payload = payload.payload
        ob, bm = self._instrument_manager.get(db_payload["instrument"], MarketType.SPOT)

        context = OrderContext(
            engine=self,
            orderbook=ob,
            balance_manager=bm,
            order_manager=self._order_manager,
        )
        return context

    def place_order(self, payload: EnginePayload) -> None:
        handler = self._order_type_handlers.get(payload.type)
        if handler and handler.can_handle(payload.type):
            payloads: list[dict] = handler.handle_new(payload.data, self)

            if payloads:
                _, bm = self._instrument_manager.get(payloads[0]["instrument"])
                map(lambda x: bm.append(x["user_id"]), payloads)
                map(self._push_order_payload, payloads)

    def modify_order(self, request: ModifyRequest) -> None:
        payload = self._payloads.get(request.order_id)
        if payload is None:
            return

        db_payload = payload.payload
        ot = db_payload["order_type"]
        handler = self._order_type_handlers.get(ot)
        if handler is None or not handler.is_modifiable():
            return

        ob, bm = self._instrument_manager.get(db_payload["instrument"])
        context = OrderContext(
            orderbook=ob,
            engine=self,
            order_manager=self._order_manager,
            balance_manager=bm,
        )
        handler.modify(request, payload, context)
        self._push_order_payload(db_payload)

    def cancel_order(self, request: CancelRequest) -> None:
        payload = self._payloads.get(request.order_id)
        if payload is None:
            return

        db_payload = payload.payload
        ob, bm = self._instrument_manager.get(db_payload["instrument"])

        ot = db_payload["order_type"]
        handler = self._order_type_handlers.get(ot)
        if handler is None:
            return

        if handler.is_cancellable():
            context = OrderContext(
                orderbook=ob,
                engine=self,
                order_manager=self._order_manager,
                balance_manager=bm,
            )
            handler.cancel(payload, context)
        else:
            order = self._order_manager.get(db_payload["order_id"])
            payload.apply_cancel(db_payload["standing_quantity"])
            ob.remove(order, order.price)
            self._order_manager.remove(db_payload["order_id"])

        self._push_order_payload(db_payload)

    def _execute_match(
        self, order: SpotOrder, payload: SpotPayload, context: OrderContext
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

        # if result.outcome != MatchOutcome.FAILURE:
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
        order: SpotOrder,
        payload: SpotPayload,
        orderbook: OrderBook,
        balance_manager: BalanceManager,
    ) -> None:
        db_payload = payload.payload
        user_id = db_payload["user_id"]

        orderbook.set_price(price)
        payload.apply_fill(quantity, price)
        order.filled_quantity += quantity

        if order.side == Side.BID:
            balance_manager.increase_balance(user_id, quantity)
        else:
            balance_manager.decrease_balance(user_id, quantity)

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
            asset_balance=balance_manager.get_balance(user_id),
            metadata={"tag": order.tag, "market_type": MarketType.SPOT},
        )

    def _handle_fill(
        self, order: SpotOrder, quantity: int, price: float, ob: OrderBook
    ) -> None:
        payload = self._payloads[order.id]
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
            order_manager=self._order_manager,
        )
        handler = self._order_type_handlers[payload.payload["order_type"]]
        handler.handle_filled(quantity, price, order, payload, context)
        self._push_order_payload(payload.payload)

    def _handle_cancel_order(
        self,
        quantity: int,
        payload: dict,
        order: SpotOrder,
        orderbook: OrderBook,
        balance_manager: BalanceManager,
    ) -> None:
        asset_balance = balance_manager.get_balance(payload["user_id"])
        is_in_book = order.quantity != order.filled_quantity

        standing_quantity = payload["standing_quantity"]
        order.quantity -= quantity
        remaining_quantity = standing_quantity - quantity
        payload["standing_quantity"] = remaining_quantity

        if remaining_quantity == 0:
            if is_in_book:
                orderbook.remove(order, order.price)

            self._order_manager.remove(order.id)
            payload["status"] = (
                OrderStatus.CANCELLED
                if payload["open_quantity"] == 0
                else OrderStatus.FILLED
            )

            if balance_manager.get_balance(payload["user_id"]) == 0:
                balance_manager.remove(payload["user_id"])

        EventService.log_order_event(
            EventType.ORDER_CANCELLED,
            payload,
            quantity=quantity,
            asset_balance=asset_balance,
        )

    def _create_payload(self, payload: dict) -> SpotPayload:
        if self._validate_new(payload):
            return self._payloads.setdefault(payload["order_id"], SpotPayload(payload))
        raise ValueError("Invalid payload.")
