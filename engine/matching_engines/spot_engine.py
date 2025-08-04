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
        self._payloads: dict[str, dict] = {}

    def _handle_match_outcome(
        self,
        result: MatchResult,
        order: SpotOrder,
        payload: dict,
        context: OrderContext,
    ) -> None:
        ob = context.orderbook
        bm = context.balance_manager

        if result.outcome == MatchOutcome.SUCCESS:
            payload["status"] = OrderStatus.FILLED
        elif result.outcome == MatchOutcome.PARTIAL:
            payload["status"] = OrderStatus.PARTIALLY_FILLED

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            context.orderbook.set_price(result.price)
            asset_balance = bm.get_balance(payload["user_id"])

            event_type = (
                EventType.ORDER_FILLED
                if result.outcome == MatchOutcome.SUCCESS
                else EventType.ORDER_PARTIALLY_FILLED
            )

            if result.outcome == MatchOutcome.SUCCESS:
                bm.remove(payload["user_id"])

            EventService.log_order_event(
                event_type,
                payload,
                quantity=result.quantity,
                price=result.price,
                asset_balance=asset_balance,
                metadata={"tag": order.tag, "market_type": MarketType.SPOT},
            )

        if result.outcome != MatchOutcome.SUCCESS:
            price = payload["limit_price"] or result.price or ob.price
            order.price = price
            ob.append(order, price)
            context.order_manager.append(order)

            self._log_order_new(
                payload,
                quantity=order.quantity - order.filled_quantity,
                price=order.price,
                asset_balance=bm.get_balance(payload["user_id"]),
            )

        self._push_order_payload(payload)

    def _execute_match(
        self, order: SpotOrder, payload: dict, context: OrderContext
    ) -> MatchResult:
        result = self._match(order, context.orderbook)

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            order.filled_quantity = result.quantity
            payload["open_quantity"] = result.quantity
            payload["standing_quantity"] = order.quantity - result.quantity
            context.balance_manager.increase_balance(
                payload["user_id"], result.quantity
            )

        self._handle_match_outcome(result, order, payload, context)
        return result

    def place_order(self, payload: dict) -> None:
        if payload["order_id"] in self._payloads:
            raise RuntimeError("Order ID already exists")

        self._payloads[payload["order_id"]] = payload
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
                orderbook=ob,
                balance_manager=bm,
                oco_manager=self._oco_manager,
                order_manager=self._order_manager,
            )
            handler.handle(order, payload, context)

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
            orderbook=ob,
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
                orderbook=ob,
                engine=self,
                oco_manager=self._oco_manager,
                order_manager=self._order_manager,
                balance_manager=bm,
            )
            handler.cancel(requested_quantity, payload, order, context)
        else:
            self._handle_cancel_order(requested_quantity, payload, order, ob, bm)

        self._push_order_payload(payload)

    def _handle_order_fill(
        self, order: SpotOrder, filled_quantity: int, price: float, ob: OrderBook
    ) -> None:
        payload = self._payloads[order.id]
        _, bm = self._instrument_manager.get(payload["instrument"])
        context = OrderContext(
            orderbook=ob,
            engine=self,
            oco_manager=self._oco_manager,
            order_manager=self._order_manager,
            balance_manager=bm,
        )

        handler = self._order_type_handlers[payload["order_type"]]
        handler.handle_filled(filled_quantity, order, payload, context)

        # return super()._handle_filled_order(order, filled_quantity, price, ob)

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
