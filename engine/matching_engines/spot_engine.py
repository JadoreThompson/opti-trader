from enums import EventType, MarketType, OrderStatus, OrderType, Side
from .base_engine import BaseEngine
from ..enums import MatchOutcome, Tag
from ..event_service import EventService
from ..managers import BalanceManager
from ..managers import InstrumentManager
from ..managers import OrderManager
from ..managers import OCOManager
from ..orderbook.orderbook import OrderBook
from ..orders import SpotOrder
from ..order_context import OrderContext
from ..order_type_handlers import (
    LimitOrderHandler,
    LimitOCOOrderHandler,
    MarketOrderHandler,
    MarketOCOOrderHandler,
    OrderTypeHandler,
)
from ..payloads import SpotPayload
from ..typing import CancelRequest, MatchResult, ModifyRequest


class SpotEngine(BaseEngine[SpotOrder]):
    def __init__(
        self,
        loop=None,
        queue=None,
        instrument_manager: InstrumentManager | None = None,
        oco_manager: OCOManager | None = None,
        order_manager: OrderManager | None = None,
    ):
        super().__init__(loop, queue)
        self._instrument_manager = instrument_manager or InstrumentManager()
        self._order_type_handlers: dict[OrderType, OrderTypeHandler] = {
            OrderType.LIMIT: LimitOrderHandler(),
            OrderType.LIMIT_OCO: LimitOCOOrderHandler(),
            OrderType.MARKET: MarketOrderHandler(),
            OrderType.MARKET_OCO: MarketOCOOrderHandler(),
        }
        self._oco_manager = oco_manager or OCOManager()
        self._order_manager = order_manager or OrderManager()
        # self._payloads: dict[str, dict] = {}
        self._payloads: dict[str, SpotPayload] = {}

    def _handle_post_match(
        self,
        result: MatchResult,
        order: SpotOrder,
        payload: SpotPayload,
        context: OrderContext,
    ) -> None:
        db_payload = payload.payload
        bm = context.balance_manager
        ob = context.order_book
        user_id = db_payload["user_id"]

        if result.outcome != MatchOutcome.FAILURE:
            ob.set_price(result.price)
            order.filled_quantity += result.quantity
            payload.apply_fill(result.quantity, result.price)

            if db_payload["side"] == Side.BID:
                bm.increase_balance(user_id, result.quantity)
            else:
                bm.decrease_balance(user_id, result.quantity)

            event_type = (
                EventType.ORDER_FILLED
                if result.outcome == MatchOutcome.SUCCESS
                else EventType.ORDER_PARTIALLY_FILLED
            )

            asset_balance = bm.get_balance(user_id)

            event_type = (
                EventType.ORDER_FILLED
                if result.outcome == MatchOutcome.SUCCESS
                else EventType.ORDER_PARTIALLY_FILLED
            )

            EventService.log_order_event(
                event_type,
                payload,
                quantity=result.quantity,
                price=result.price,
                asset_balance=asset_balance,
                metadata={"tag": order.tag, "market_type": MarketType.SPOT},
            )

    def _execute_match(
        self, order: SpotOrder, payload: SpotPayload, context: OrderContext
    ) -> MatchResult:
        result = self._match(order, context.order_book)
        self._handle_post_match(
            result=result, order=order, payload=payload, context=context
        )
        return result

    def place_order(self, payload: dict) -> None:
        if payload["order_id"] in self._payloads:
            raise RuntimeError("Order ID already exists")

        # self._payloads[payload["order_id"]] = payload
        spot_payload = SpotPayload(payload)
        self._payloads[payload["order_id"]] = spot_payload
        ot = payload["order_type"]
        ob, bm = self._instrument_manager.get(payload["instrument"], MarketType.SPOT)

        if (
            payload["side"] == Side.ASK
            and bm.get_balance(payload["user_id"]) < payload["quantity"]
        ):
            EventService.log_rejection(
                payload, asset_balance=bm.get_balance(payload["user_id"])
            )
            return

        handler = self._order_type_handlers.get(ot)
        if handler and handler.can_handle(ot):
            order = SpotOrder(
                payload["order_id"], Tag.ENTRY, payload["side"], payload["quantity"]
            )
            context = OrderContext(
                engine=self,
                order_book=ob,
                balance_manager=bm,
                oco_manager=self._oco_manager,
                order_manager=self._order_manager,
            )
            handler.handle(order, spot_payload, context)

        self._push_order_payload(payload)

    def modify_order(self, request: ModifyRequest) -> None:
        payload = self._payloads.get(request.order_id)
        if payload is None:
            return

        ot = payload["order_type"]
        handler = self._order_type_handlers.get(ot)
        if handler is None or not handler.is_modifiable():
            return

        ob, bm = self._instrument_manager.get(payload["instrument"])
        context = OrderContext(
            order_book=ob,
            engine=self,
            oco_manager=self._oco_manager,
            order_manager=self._order_manager,
            balance_manager=bm,
        )
        handler.modify(request, payload, context)
        self._push_order_payload(payload)

    def cancel_order(self, request: CancelRequest) -> None:
        payload = self._payloads.get(request.order_id, {})
        standing_quantity = payload.get("standing_quantity", 0)

        if standing_quantity == 0:
            return

        requested_quantity = self._validate_close_req_quantity(
            request.quantity, standing_quantity
        )
        ob, bm = self._instrument_manager.get(payload["instrument"])
        order = self._order_manager.get(request.order_id)

        if order is None:
            EventService.log_rejection(
                payload, asset_balance=bm.get_balance(payload["user_id"])
            )
            return

        ot = payload["order_type"]
        handler = self._order_type_handlers.get(ot)
        if handler is None:
            return

        if handler.is_cancellable():
            context = OrderContext(
                order_book=ob,
                engine=self,
                oco_manager=self._oco_manager,
                order_manager=self._order_manager,
                balance_manager=bm,
            )
            handler.cancel(requested_quantity, payload, order, context)
        else:
            self._handle_cancel_order(requested_quantity, payload, order, ob, bm)

        self._push_order_payload(payload)

    def _handle_fill(
        self, order: SpotOrder, quantity: int, price: float, ob: OrderBook
    ) -> None:
        payload = self._payloads[order.id]
        db_payload = payload.payload
        user_id = db_payload["user_id"]
        _, bm = self._instrument_manager.get(payload.payload["instrument"])

        if db_payload["side"] == Side.BID:
            bm.increase_balance(user_id, quantity)
        else:
            bm.decrease_balance(user_id, quantity)

        payload.apply_fill(quantity, price)

        etype = (
            EventType.ORDER_FILLED
            if db_payload["standing_quantity"] == 0
            else EventType.ORDER_PARTIALLY_FILLED
        )
        EventService.log_order_event(
            etype,
            payload,
            asset_balance=bm.get_balance(user_id),
            price=price,
            quantity=quantity,
            metadata={"market_type": MarketType.SPOT},
        )

        context = OrderContext(
            order_book=ob,
            engine=self,
            oco_manager=self._oco_manager,
            order_manager=self._order_manager,
            balance_manager=bm,
        )

        handler = self._order_type_handlers[payload.payload["order_type"]]
        handler.handle_filled(quantity, price, order, payload, context)

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

        self._push_order_payload(payload)
