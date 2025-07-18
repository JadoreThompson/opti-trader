import json
from pprint import pprint
from pydantic import ValidationError
from config import REDIS, SPOT_QUEUE_KEY
from enums import OrderType, Side
from .base_engine import BaseEngine
from ..balance_manager import BalanceManager
from ..enums import MatchOutcome, Tag
from ..orders.oco_order import OCOOrder
from ..orders.spot_order import SpotOrder
from ..oco_manager import OCOManager
from ..orderbook import OrderBook
from ..order_manager import OrderManager
from ..typing import (
    MODIFY_DEFAULT,
    ModifyRequest,
    MatchResult,
    CloseRequest,
    Payload,
    PayloadTopic,
    Event,
    EventType,
)
from ..tasks import log_event


class SpotEngine(BaseEngine[SpotOrder]):
    def __init__(
        self,
        loop=None,
        oco_manager: OCOManager = None,
        balance_manager: BalanceManager = None,
        order_manager: OrderManager = None,
    ):
        super().__init__(loop)
        self._oco_manager = oco_manager or OCOManager()
        self._balance_manager = balance_manager or BalanceManager()
        self._order_manager = order_manager or OrderManager()
        self._order_payloads: dict[str, dict] = {}

    async def run(self) -> None:
        async with REDIS.pubsub() as ps:
            await ps.subscribe(SPOT_QUEUE_KEY)
            async for m in ps.listen():
                if m["type"] == "subscribe":
                    continue

                try:
                    payload = Payload(**m["data"])

                    if payload.topic == PayloadTopic.CREATE:
                        self.place_order(payload.data)
                    elif payload.topic == PayloadTopic.CANCEL:
                        self.cancel_order(CloseRequest(**payload.data))
                    elif payload.topic == PayloadTopic.MODIFY:
                        self.modify_order(ModifyRequest(**payload.data))
                except ValidationError:
                    pass

    def place_order(self, payload: dict) -> None:
        """
        Places a new order in the engine.
        """
        ob = self._orderbooks.setdefault(payload["instrument"], OrderBook())
        self._order_payloads[payload["order_id"]] = payload
        self._balance_manager.append(payload["user_id"])
        # pprint(f"BalanceManager:\n{json.dumps(self._balance_manager._users)}")
        # pprint(payload)
        # print("", end="\n\n")
        order = SpotOrder(
            payload["order_id"], Tag.ENTRY, payload["side"], payload["quantity"]
        )

        if payload["stop_loss"] is not None or payload["take_profit"] is not None:
            self._handle_place_oco_order(order, payload, ob)
            return

        if payload["order_type"] == OrderType.LIMIT and not (
            (
                order.side == Side.BID
                and ob.best_ask is not None
                and payload["limit_price"] >= ob.best_ask
            )
            or (
                order.side == Side.ASK
                and ob.best_bid is not None
                and payload["limit_price"] <= ob.best_bid
            )
        ):
            order.price = payload["limit_price"]
            ob.append(order, order.price)
            self._order_manager.append(order)
            log_event.delay(
                Event(
                    event_type=EventType.ORDER_PLACED,
                    user_id=payload["user_id"],
                    order_id=order.id,
                    quantity=order.quantity,
                    price=order.price,
                    asset_balance=self._balance_manager.get_balance(payload["user_id"]),
                    metadata={"tag": order.tag},
                ).model_dump()
            )
            return

        result: MatchResult = self._match(order, ob)
        order.filled_quantity = result.quantity

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            ob.set_price(result.price)
            self._update_price(payload["instrument"], result.price)

            event_type = (
                EventType.ORDER_FILLED
                if result.outcome == MatchOutcome.SUCCESS
                else EventType.ORDER_PARTIALLY_FILLED
            )

            log_event.delay(
                Event(
                    event_type=event_type,
                    quantity=result.quantity,
                    price=result.price,
                    user_id=payload["user_id"],
                    order_id=payload["order_id"],
                    asset_balance=self._balance_manager.get_balance(payload["user_id"]),
                    metadata={"tag": order.tag},
                ).model_dump()
            )

            if result.outcome == MatchOutcome.SUCCESS:
                self._balance_manager.remove(payload["order_id"])
                return

        price = payload["limit_price"] or result.price or ob.price
        order.price = price
        ob.append(order, price)
        self._order_manager.append(order)

        log_event.delay(
            Event(
                event_type=EventType.ORDER_PLACED,
                user_id=payload["user_id"],
                order_id=order.id,
                quantity=order.quantity - order.filled_quantity,
                price=order.price,
                asset_balance=self._balance_manager.get_balance(payload["user_id"]),
            ).model_dump()
        )

    def cancel_order(self, request: CloseRequest) -> None:
        """Cancel or reduce an existing order."""
        order = self._order_manager.get(request.order_id)
        payload = self._order_payloads[order.id]
        ob = self._orderbooks[payload["instrument"]]

        # Order is fully filled. Cannot perform cancel.
        if payload["standing_quantity"] == 0:
            return

        standing_quantity = payload["standing_quantity"]
        requested_quantity = self._validate_close_req_quantity(
            request.quantity, standing_quantity
        )
        remaining_quantity = standing_quantity - requested_quantity
        payload["standing_quantity"] = remaining_quantity
        entry_in_book = order.quantity != order.filled_quantity
        order.quantity -= requested_quantity

        if remaining_quantity == 0:
            if entry_in_book:
                ob.remove(order, order.price)

            if payload["open_quantity"] == 0 and order.oco_id is not None:
                self._remove_tp_sl(self._oco_manager.get(order.oco_id), ob)
                self._oco_manager.remove(order.oco_id)

        log_event.delay(
            Event(
                event_type=EventType.ORDER_CANCELLED,
                quantity=requested_quantity,
                user_id=payload["user_id"],
                order_id=payload["order_id"],
                asset_balance=self._balance_manager.get_balance(payload["user_id"]),
            ).model_dump()
        )

    def modify_order(self, request: ModifyRequest) -> None:
        order = self._order_manager.get(request.order_id)
        payload = self._order_payloads[order.id]
        ob = self._orderbooks[payload["instrument"]]

        if (
            request.limit_price != MODIFY_DEFAULT
            and payload["limit_price"] != request.limit_price
            and payload["standing_quantity"] != 0
            and payload["order_type"] == OrderType.LIMIT
        ):
            ob.remove(order, order.price)
            if request.limit_price is not None:
                payload["limit_price"] = request.limit_price
                order.price = request.limit_price
                ob.append(order, order.price)

        if order.oco_id is not None:
            oco_order = self._oco_manager.get(order.oco_id)
            if (
                request.take_profit is not MODIFY_DEFAULT
                and request.take_profit != payload["take_profit"]
            ):
                payload["take_profit"] = request.take_profit
                tp_order = oco_order.leg_c

                if tp_order is not None:
                    ob.remove(tp_order, tp_order.price)
                if request.take_profit is None:
                    oco_order.leg_c = None
                else:
                    if tp_order is None:
                        tp_order = SpotOrder(
                            order.id,
                            Tag.TAKE_PROFIT,
                            Side.ASK,
                            payload["open_quantity"],
                            oco_id=order.oco_id,
                        )
                        oco_order.leg_c = tp_order
                    tp_order.price = request.take_profit
                    ob.append(tp_order, tp_order.price)

            if (
                request.stop_loss is not MODIFY_DEFAULT
                and request.stop_loss != payload["stop_loss"]
            ):
                payload["stop_loss"] = request.stop_loss
                sl_order = oco_order.leg_b

                if sl_order is not None:
                    ob.remove(sl_order, sl_order.price)
                if request.stop_loss is None:
                    oco_order.leg_b = None
                else:
                    if sl_order is None:
                        sl_order = SpotOrder(
                            order.id,
                            Tag.STOP_LOSS,
                            Side.ASK,
                            payload["open_quantity"],
                            oco_id=order.oco_id,
                        )
                        oco_order.leg_b = sl_order

                    sl_order.price = request.stop_loss
                    ob.append(sl_order, sl_order.price)

        log_event.delay(
            Event(
                event_type=EventType.ORDER_MODIFIED,
                user_id=payload["user_id"],
                order_id=payload["order_id"],
                asset_balance=self._balance_manager.get_balance(payload["user_id"]),
                **request.model_dump(exclude_unset=True),
            ).model_dump()
        )

    def _handle_place_oco_order(
        self, order: SpotOrder, payload: dict, ob: OrderBook[SpotOrder]
    ) -> None:
        """Place an order with OCO (One-Cancels-Other) handling."""
        oco_order: OCOOrder = self._oco_manager.create()
        payload["oco_id"] = oco_order.id
        order.set_oco_id(oco_order.id)
        oco_order.leg_a = order
        self._order_manager.append(order)

        is_crossable = (
            order.side == Side.BID
            and ob.best_ask is not None
            and payload["limit_price"] >= ob.best_ask
        ) or (
            order.side == Side.ASK
            and ob.best_bid is not None
            and payload["limit_price"] <= ob.best_bid
        )

        if payload["order_type"] == OrderType.LIMIT and not is_crossable:
            order.price = payload["limit_price"]
            ob.append(order, order.price)
            log_event.delay(
                Event(
                    event_type=EventType.ORDER_PLACED,
                    user_id=payload["user_id"],
                    order_id=order.id,
                    quantity=order.quantity,
                    price=order.price,
                    asset_balance=self._balance_manager.get_balance(payload["user_id"]),
                ).model_dump()
            )
            return

        result: MatchResult = self._match(order, ob)
        order.filled_quantity = result.quantity

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            ob.set_price(result.price)
            self._update_price(payload["instrument"], result.price)
            self._place_tp_sl(oco_order, ob)

            log_event.delay(
                Event(
                    event_type=(
                        EventType.ORDER_FILLED
                        if result.outcome == MatchOutcome.SUCCESS
                        else EventType.ORDER_PARTIALLY_FILLED
                    ),
                    quantity=result.quantity,
                    price=result.price,
                    user_id=payload["user_id"],
                    order_id=payload["order_id"],
                    asset_balance=self._balance_manager.get_balance(payload["user_id"]),
                    metadata={"tag": order.tag},
                ).model_dump()
            )

            if result.outcome == MatchOutcome.SUCCESS:
                return

        price = payload["limit_price"] or result.price or ob.price
        order.price = price
        ob.append(order, price)

        log_event.delay(
            Event(
                event_type=EventType.ORDER_PLACED,
                user_id=payload["user_id"],
                order_id=order.id,
                quantity=order.quantity - order.filled_quantity,
                price=order.price,
                asset_balance=self._balance_manager.get_balance(payload["user_id"]),
            ).model_dump()
        )

    def _process_trade_fill(
        self, order: SpotOrder, filled_quantity: int, payload: dict
    ) -> None:
        user_id = payload["user_id"]

        if order.tag in (Tag.STOP_LOSS, Tag.TAKE_PROFIT):
            payload["open_quantity"] -= filled_quantity
            self._balance_manager.decrease_balance(user_id, filled_quantity)
        elif order.side == Side.BID:
            payload["open_quantity"] += filled_quantity
            payload["standing_quantity"] -= filled_quantity
            self._balance_manager.increase_balance(user_id, filled_quantity)
        else:
            payload["open_quantity"] += filled_quantity
            payload["standing_quantity"] -= filled_quantity
            self._balance_manager.decrease_balance(user_id, filled_quantity)

    def _handle_filled_order(
        self,
        order: SpotOrder,
        filled_quantity: int,
        price: float,
        ob: OrderBook[SpotOrder],
    ) -> None:
        """Handle a resting order that was fully filled."""
        payload = self._order_payloads[order.id]
        self._process_trade_fill(order, filled_quantity, payload)

        log_event.delay(
            Event(
                event_type=EventType.ORDER_FILLED,
                user_id=payload["user_id"],
                order_id=order.id,
                quantity=filled_quantity,
                price=price,
                asset_balance=self._balance_manager.get_balance(payload["user_id"]),
                metadata={"tag": order.tag},
            ).model_dump()
        )

        if order.tag == Tag.ENTRY:
            ob.remove(order, order.price)
            if order.oco_id is not None:
                oco_order = self._oco_manager.get(order.oco_id)
                if oco_order.leg_b is None and oco_order.leg_c is None:
                    self._place_tp_sl(oco_order, ob)
                else:
                    self._mutate_tp_sl(oco_order, payload["open_quantity"])
            else:
                self._balance_manager.remove(order.id)
                self._order_manager.remove(order.id)
        else:
            oco_order = self._oco_manager.get(order.oco_id)
            self._remove_tp_sl(oco_order, ob)
            if payload["open_quantity"] == 0 and payload["standing_quantity"] == 0:
                self._oco_manager.remove(oco_order.id)
                self._balance_manager.remove(order.id)
                self._order_manager.remove(order.id)

    def _handle_touched_order(
        self,
        order: SpotOrder,
        touched_quantity: int,
        price: float,
        ob: OrderBook[SpotOrder],
    ) -> None:
        """Handle a resting order that was partially filled (touched)."""
        payload = self._order_payloads[order.id]
        self._process_trade_fill(order, touched_quantity, payload)

        if order.side == Side.BID or (
            order.side == Side.ASK and order.tag == Tag.ENTRY
        ):
            balance_update = self._balance_manager.increase_balance(
                order.id, touched_quantity
            )
        else:
            balance_update = self._balance_manager.decrease_balance(
                order.id, touched_quantity
            )

        log_event.delay(
            Event(
                event_type=EventType.ORDER_PARTIALLY_FILLED,
                user_id=payload["user_id"],
                order_id=order.id,
                quantity=touched_quantity,
                price=price,
                asset_balance=self._balance_manager.get_balance(payload["user_id"]),
                metadata={"tag": order.tag.value},
            ).model_dump()
        )

        if order.oco_id is not None:
            oco_order = self._oco_manager.get(order.oco_id)
            if oco_order.leg_b is None and oco_order.leg_c is None:
                self._place_tp_sl(oco_order, ob)
            else:
                self._mutate_tp_sl(oco_order, payload["open_quantity"])

    def _place_tp_sl(self, oco_order: OCOOrder, ob: OrderBook[SpotOrder]) -> None:
        """
        Place take-profit and stop-loss orders for an OCO order.

        Creates and appends TP and/or SL orders based on the payload linked
        to the entry order.

        Args:
            oco_order (OCOOrder): OCO container for the TP/SL legs.
            ob (OrderBook[SpotOrder]): Order book for appending the TP/SL orders.
        """
        entry_order = oco_order.leg_a
        payload = self._order_payloads["entry_order.id"]

        if payload["stop_loss"] is not None:
            new_order = SpotOrder(
                payload["order_id"],
                Tag.STOP_LOSS,
                Side.ASK,
                payload["open_quantity"],
                payload["stop_loss"],
                oco_id=oco_order.id,
            )
            ob.append(new_order, new_order.price)
            oco_order.leg_b = new_order

        if payload["take_profit"] is not None:
            new_order = SpotOrder(
                payload["order_id"],
                Tag.TAKE_PROFIT,
                Side.ASK,
                payload["open_quantity"],
                payload["take_profit"],
                oco_id=oco_order.id,
            )
            ob.append(new_order, new_order.price)
            oco_order.leg_c = new_order

    def _mutate_tp_sl(self, oco_order: OCOOrder, open_quantity: int) -> None:
        """Update quantities of TP and SL legs in an OCO order.

        Args:
            oco_order (OCOOrder): OCO container holding TP/SL legs.
            open_quantity (int): New open quantity to apply.
        """
        if oco_order.leg_b is not None:
            oco_order.leg_b.quantity = open_quantity
        if oco_order.leg_c is not None:
            oco_order.leg_c.quantity = open_quantity

    def _remove_tp_sl(self, oco_order: OCOOrder, ob: OrderBook[SpotOrder]) -> None:
        """Remove TP and SL orders from an OCO order.

        Cleans up associated TP/SL legs from the order book and clears them
        from the OCO container.

        Args:
            oco_order (OCOOrder): OCO container holding TP/SL legs.
            ob (OrderBook[SpotOrder]): Order book from which to remove the legs.
        """
        if oco_order.leg_b is not None:
            ob.remove(oco_order.leg_b, oco_order.leg_b.price)
            oco_order.leg_b = None
        if oco_order.leg_c is not None:
            ob.remove(oco_order.leg_c, oco_order.leg_c.price)
            oco_order.leg_c = None
