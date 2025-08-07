from typing import Any

from enums import EventType, Side
from ..enums import MatchOutcome, Tag
from ..event_service import EventService
from ..orderbook import OrderBook
from ..orders import Order, SpotOrder
from ..order_context import OrderContext
from ..typing import OrderEnginePayloadData, MatchResult


class LimitMixin:
    @staticmethod
    def _is_crossable(order: Order, payload: dict, ob: OrderBook) -> bool:
        return (
            order.side == Side.BID
            and ob.best_ask is not None
            and payload["limit_price"] >= ob.best_ask
        ) or (
            order.side == Side.ASK
            and ob.best_bid is not None
            and payload["limit_price"] <= ob.best_bid
        )

    def _handle_new_order(
        self,
        data: OrderEnginePayloadData,
        engine: "Engine",
    ) -> tuple[SpotOrder, Any, OrderContext, bool]:
        """
        Checks if order is crossable. If it is, attempts
        to fill order at best opposite price. Any remaining
        quantity is placed into the book which is the same
        when the order isn't crossable.

        Args:
            data (MarketLimitEnginePayloadData): Object containing
                the db record dict.
            engine (Engine): Matching engine being used.

        Returns:
            tuple[SpotOrder, Any, OrderContext, bool]:
                SpotOrder: The order object created.
                Any: Object of type engine._payload_class wrapping the payload.
                OrderContext: Context for execution.
                bool:
                    - True: Order was placed in book.
                    - False: Order wasn't placed in book.
        """
        db_payload = data.order
        payload = engine._create_payload(db_payload)
        order = engine._order_cls(
            id_=db_payload["order_id"],
            tag=Tag.ENTRY,
            side=db_payload["side"],
            quantity=db_payload["quantity"],
        )

        context = engine._build_context(payload)
        ob = context.orderbook

        if self._is_crossable(order, db_payload, ob):
            result: MatchResult = engine._execute_match(order, payload, context)
            if result.outcome == MatchOutcome.SUCCESS:
                return (order, payload, context, False)

        order.price = db_payload["limit_price"]
        ob.append(order, order.price)
        EventService.log_order_event(
            EventType.ORDER_PLACED,
            db_payload,
            quantity=db_payload["quantity"],
            asset_balance=context.balance_manager.get_balance(db_payload["user_id"]),
        )
        return (order, payload, context, True)
