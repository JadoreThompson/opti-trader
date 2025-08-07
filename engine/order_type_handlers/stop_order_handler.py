from enums import EventType, OrderType, Side
from .order_type_handler import OrderTypeHandler
from ..event_service import EventService
from ..enums import MatchOutcome, Tag
from ..matching_engines import Engine
from ..orderbook import OrderBook
from ..order_context import OrderContext
from ..orders import SpotOrder
from ..payloads import SpotPayload, PayloadProtocol
from ..typing import ModifyRequest, OrderEnginePayloadData


class StopOrderHandler(OrderTypeHandler):
    @staticmethod
    def is_modifiable() -> bool:
        return True

    def can_handle(self, order_type: OrderType) -> bool:
        return order_type == OrderType.STOP

    def handle_new(self, data: OrderEnginePayloadData, engine: Engine) -> None:
        db_payload = data.order
        payload = engine._create_payload(db_payload)
        context = engine._build_context(payload)
        order = engine._order_cls(
            id_=db_payload["order_id"],
            tag=Tag.ENTRY,
            side=db_payload["side"],
            quantity=db_payload["quantity"],
        )

        if self._is_crossable(order, db_payload, context.orderbook):
            result = engine._execute_match(order, payload, context)
            # print(result)

            if result.outcome == MatchOutcome.SUCCESS:
                return [db_payload]

        context.order_manager.append(order)
        order.price = db_payload["stop_price"]
        context.orderbook.append(order, order.price)
        EventService.log_order_event(
            EventType.ORDER_PLACED,
            db_payload,
            quantity=db_payload["quantity"],
            asset_balance=context.balance_manager.get_balance(db_payload["user_id"]),
        )

        return [db_payload]

    def handle_filled(
        self,
        quantity: int,
        price: float,
        order: SpotOrder,
        payload: SpotPayload,
        context: OrderContext,
    ) -> None:
        if order.filled_quantity == order.quantity:
            context.orderbook.remove(order, order.price)
            context.order_manager.remove(order.id)

    def modify(
        self, request: ModifyRequest, payload: PayloadProtocol, context: OrderContext
    ) -> None:
        ob = context.orderbook
        db_payload = payload.payload
        order = context.order_manager.get(db_payload["order_id"])
        if order is None:
            return

        if self._is_crossable(order, db_payload, ob):
            EventService.log_rejection(
                payload,
                asset_balance=context.balance_manager.get_balance(
                    db_payload["user_id"]
                ),
            )
            return

        db_payload["stop_price"] = request.stop_price
        ob.remove(order, order.price)
        order.price = request.stop_price
        ob.append(order, order.price)

    @staticmethod
    def _is_crossable(order: SpotOrder, payload: dict, ob: OrderBook) -> bool:
        return (
            order.side == Side.BID
            and ob.best_ask is not None
            and payload["stop_price"] <= ob.best_ask
        ) or (
            order.side == Side.ASK
            and ob.best_bid is not None
            and payload["stop_price"] >= ob.best_bid
        )
