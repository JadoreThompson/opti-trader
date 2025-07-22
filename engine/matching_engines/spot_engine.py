import logging

from json import loads
from pydantic import ValidationError

from config import REDIS_CLIENT, SPOT_QUEUE_KEY
from enums import OrderStatus, OrderType, Side
from services.payload_pusher.typing import PusherPayload, PusherPayloadTopic
from utils.utils import get_exc_line
from .base_engine import BaseEngine
from ..balance_manager import BalanceManager
from ..enums import MatchOutcome, Tag
from ..orders.oco_order import OCOOrder
from ..orders.spot_order import SpotOrder
from ..oco_manager import OCOManager
from ..orderbook import OrderBook
from ..order_manager import OrderManager
from ..typing import (
    MODIFY_SENTINEL,
    ModifyRequest,
    MatchResult,
    CloseRequest,
    Payload,
    PayloadTopic,
    Event,
    EventType,
    SupportsAppend,
    Queue,
)
from ..tasks import log_event

logger = logging.getLogger(__file__)


class SpotEngine(BaseEngine[SpotOrder]):
    def __init__(
        self,
        loop=None,
        oco_manager: OCOManager = None,
        order_manager: OrderManager = None,
        payload_queue: SupportsAppend = None,
    ):
        super().__init__(loop)
        self._oco_manager = oco_manager or OCOManager()
        self._order_manager = order_manager or OrderManager()
        self._order_payloads: dict[str, dict] = {}
        self._payload_queue = payload_queue or Queue()
        self._orderbooks = {}

    async def run(self) -> None:
        async with REDIS_CLIENT.pubsub() as ps:
            await ps.subscribe(SPOT_QUEUE_KEY)
            async for m in ps.listen():
                if m["type"] == "subscribe":
                    continue

                try:
                    payload = Payload(**loads(m["data"]))

                    if payload.topic == PayloadTopic.CREATE:
                        self.place_order(payload.data)
                    elif payload.topic == PayloadTopic.CANCEL:
                        self.cancel_order(CloseRequest(**payload.data))
                    elif payload.topic == PayloadTopic.MODIFY:
                        self.modify_order(ModifyRequest(**payload.data))

                except ValidationError as e:
                    logger.error(
                        f"Error: {type(e)} - {str(e)} - line: {get_exc_line()}"
                    )
                    pass

    def place_order(self, payload: dict) -> None:
        """
        Places a new order in the engine.
        """

        ob, balance_manager = self._orderbooks.setdefault(
            payload["instrument"], (OrderBook(), BalanceManager())
        )

        if payload["side"] == Side.ASK:
            cur_balance = balance_manager.get_balance(payload["user_id"])
            if cur_balance is None or cur_balance < payload["quantity"]:
                print("waving", cur_balance)
                log_event.delay(
                    Event(
                        event_type=EventType.ORDER_REJECTED,
                        order_id=payload["order_id"],
                        user_id=payload["user_id"],
                        asset_balance=cur_balance or 0,
                    ).model_dump()
                )
                return

        self._order_payloads[payload["order_id"]] = payload
        balance_manager.append(payload["user_id"])

        order = SpotOrder(
            payload["order_id"], Tag.ENTRY, payload["side"], payload["quantity"]
        )

        if payload["order_type"] in (OrderType.LIMIT_OCO, OrderType.MARKET_OCO):
            self._handle_place_oco_order(order, payload, ob, balance_manager)
            return

        if payload["order_type"] == OrderType.LIMIT and not (  # Crossable?
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
                    asset_balance=balance_manager.get_balance(payload["user_id"]),
                    metadata={"tag": order.tag},
                ).model_dump()
            )
            return

        result: MatchResult = self._match(order, ob)

        if result.quantity:
            order.filled_quantity = result.quantity
            payload["open_quantity"] = result.quantity
            payload["standing_quantity"] = order.quantity - result.quantity
            balance_manager.increase_balance(payload["user_id"], result.quantity)

        if result.outcome == MatchOutcome.SUCCESS:
            payload["status"] = OrderStatus.FILLED
        elif result.outcome == MatchOutcome.PARTIAL:
            payload["status"] = OrderStatus.PARTIALLY_FILLED

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            ob.set_price(result.price)
            self._update_price(payload["instrument"], result.price)

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
                    asset_balance=balance_manager.get_balance(payload["user_id"]),
                    metadata={"tag": order.tag},
                ).model_dump()
            )

        if result.outcome == MatchOutcome.SUCCESS:
            balance_manager.remove(payload["user_id"])
        else:
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
                    asset_balance=balance_manager.get_balance(payload["user_id"]),
                ).model_dump()
            )

        self._push_to_queue(payload)

    def cancel_order(self, request: CloseRequest) -> None:
        """Cancel or reduce an existing order."""
        order = self._order_manager.get(request.order_id)
        payload = self._order_payloads[order.id]
        ob, balance_manager = self._orderbooks[payload["instrument"]]

        if payload["standing_quantity"] == 0:
            return

        asset_balance = balance_manager.get_balance(payload["user_id"])
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

            if order.oco_id is None:
                self._order_manager.remove(order.id)

            if payload["open_quantity"] == 0:
                payload["status"] = OrderStatus.CANCELLED

                if order.oco_id is not None:
                    self._remove_tp_sl(self._oco_manager.get(order.oco_id), ob)
                    self._oco_manager.remove(order.oco_id)
            else:
                payload["status"] = OrderStatus.FILLED

            if balance_manager.get_balance(payload["user_id"]) == 0:
                balance_manager.remove(payload["user_id"])

        log_event.delay(
            Event(
                event_type=EventType.ORDER_CANCELLED,
                quantity=requested_quantity,
                user_id=payload["user_id"],
                order_id=payload["order_id"],
                asset_balance=asset_balance,
            ).model_dump()
        )

        if payload["status"] == OrderStatus.FILLED:
            log_event.delay(
                Event(
                    event_type=EventType.ORDER_FILLED,
                    quantity=requested_quantity,
                    user_id=payload["user_id"],
                    order_id=payload["order_id"],
                    asset_balance=asset_balance,
                ).model_dump()
            )
        self._push_to_queue(payload)

    def modify_order(self, request: ModifyRequest) -> None:
        """
        Modifies the properties of an order. If necessary
        alters the postiion of it's TP, SL and/or entry order
        if order was a LIMIT order.

        Args:
            request (ModifyRequest): ModifyRequest containing the details.
        """

        def reject_request(payload: dict, asset_balance: int) -> None:
            log_event.delay(
                Event(
                    event_type=EventType.ORDER_REJECTED,
                    order_id=payload["order_id"],
                    user_id=payload["user_id"],
                    asset_balance=asset_balance,
                ).model_dump()
            )

        payload = self._order_payloads.get(request.order_id)
        if payload is None or payload["order_type"] == OrderType.MARKET:
            return

        order = self._order_manager.get(request.order_id)
        if order is None:
            return

        is_limit_order = payload["order_type"] in (OrderType.LIMIT, OrderType.LIMIT_OCO)
        is_oco_order = payload["order_type"] in (
            OrderType.LIMIT_OCO,
            OrderType.MARKET_OCO,
        )
        is_filled = payload["standing_quantity"] == 0

        sentinel = float("inf")
        updated_limit_price = sentinel
        updated_tp_price = sentinel
        updated_sl_price = sentinel

        if is_limit_order and not is_filled and request.limit_price != MODIFY_SENTINEL:
            updated_limit_price = request.limit_price
        if is_oco_order and request.take_profit != MODIFY_SENTINEL:
            updated_tp_price = request.take_profit
        if is_oco_order and request.stop_loss != MODIFY_SENTINEL:
            updated_sl_price = request.stop_loss

        ob, balance_manager = self._orderbooks[payload["instrument"]]
        asset_balance = balance_manager.get_balance(payload["user_id"])
        ob_price: float | None = ob.price

        tmp_sl_price = (
            updated_sl_price
            if updated_sl_price != sentinel
            else (
                payload["stop_loss"]
                if payload["stop_loss"] is not None
                else float("-inf") if payload["side"] == Side.BID else float("inf")
            )
        )

        tmp_tp_price = (
            updated_tp_price
            if updated_tp_price != sentinel
            else (
                payload["take_profit"]
                if payload["take_profit"] is not None
                else float("inf") if payload["side"] == Side.BID else float("-inf")
            )
        )

        if is_limit_order:
            tmp_limit_price = (
                updated_limit_price
                if updated_limit_price != sentinel
                else (payload["limit_price"] if not is_filled else (ob_price or 0) - 1)
            )
        else:
            tmp_limit_price = sentinel

        if is_limit_order:

            if (
                is_filled
                and payload["side"] == Side.BID
                and not (tmp_sl_price < tmp_tp_price)
            ):
                return reject_request(payload, asset_balance)

            if (
                is_filled
                and payload["side"] == Side.ASK
                and not (tmp_sl_price > tmp_tp_price)
            ):
                return reject_request(payload, asset_balance)

            if (
                not is_filled
                and payload["side"] == Side.BID
                and not (tmp_sl_price < tmp_limit_price <= ob_price < tmp_tp_price)
            ):
                return reject_request(payload, asset_balance)

            if (
                not is_filled
                and payload["side"] == Side.ASK
                and not (tmp_sl_price > tmp_limit_price >= ob_price > tmp_tp_price)
            ):
                return reject_request(payload, asset_balance)
        elif is_oco_order:
            if (
                is_filled
                and payload["side"] == Side.BID
                and not (tmp_sl_price < tmp_tp_price)
            ):
                return reject_request(payload, asset_balance)

            if (
                is_filled
                and payload["side"] == Side.ASK
                and not (tmp_sl_price > tmp_tp_price)
            ):
                return reject_request(payload, asset_balance)

            if (
                not is_filled
                and payload["side"] == Side.BID
                and not (updated_sl_price < ob_price < updated_tp_price)
            ):
                return reject_request(payload, asset_balance)

            if (
                not is_filled
                and payload["side"] == Side.ASK
                and not (updated_sl_price > ob_price > updated_tp_price)
            ):
                return reject_request(payload, asset_balance)

        oco_order = self._oco_manager.get(order.oco_id)

        if is_limit_order and not is_filled:
            self._order_manager.remove(payload["order_id"])

            ob.remove(order, order.price)
            order = SpotOrder(
                order.id,
                Tag.ENTRY,
                Side.BID,
                payload["quantity"],
                tmp_limit_price,
                oco_id=order.oco_id,
            )
            self._order_manager.append(order)
            ob.append(order, order.price)

            if oco_order is not None:
                oco_order.leg_a = order

        if oco_order is not None:
            if tmp_sl_price != float("-inf"):
                if oco_order.leg_b is not None:
                    ob.remove(oco_order.leg_b, oco_order.leg_b.price)

                oco_order.leg_b = SpotOrder(
                    order.id,
                    Tag.STOP_LOSS,
                    Side.ASK,
                    payload["open_quantity"],
                    tmp_sl_price,
                    oco_id=order.oco_id,
                )
                ob.append(oco_order.leg_b, oco_order.leg_b.price)

            if tmp_tp_price is not None:
                if oco_order.leg_c is not None:
                    ob.remove(oco_order.leg_c, oco_order.leg_c.price)
                if updated_tp_price is not None:
                    oco_order.leg_c = SpotOrder(
                        order.id,
                        Tag.TAKE_PROFIT,
                        Side.ASK,
                        payload["open_quantity"],
                        tmp_tp_price,
                        oco_id=order.oco_id,
                    )
                    ob.append(oco_order.leg_c, oco_order.leg_c.price)

        if is_limit_order and not is_filled:
            if updated_limit_price == sentinel:
                payload["limit_price"] = payload["limit_price"]
            else:
                payload["limit_price"] = updated_limit_price

        payload["stop_loss"] = (
            updated_sl_price if updated_sl_price != sentinel else payload["stop_loss"]
        )
        payload["take_profit"] = (
            updated_tp_price if updated_tp_price != sentinel else payload["take_profit"]
        )

        log_event.delay(
            Event(
                event_type=EventType.ORDER_MODIFIED,
                user_id=payload["user_id"],
                order_id=payload["order_id"],
                asset_balance=asset_balance,
                limit_price=payload["limit_price"],
                stop_loss=payload["stop_loss"],
                take_profit=payload["take_profit"],
            ).model_dump()
        )

        self._push_to_queue(payload)

    def _update_or_remove_leg(
        self, price: float | None, order: SpotOrder, ob: OrderBook[SpotOrder]
    ) -> None:
        ob.remove(order, order.price)

        if price is not None:
            order.price = price
            ob.append(order, order.price)

    def _handle_place_oco_order(
        self,
        order: SpotOrder,
        payload: dict,
        ob: OrderBook[SpotOrder],
        balance_manager: BalanceManager,
    ) -> None:
        """Place an order with OCO (One-Cancels-Other) handling."""

        def place_order_event(asset_balance: int):
            log_event.delay(
                Event(
                    event_type=EventType.ORDER_PLACED,
                    user_id=payload["user_id"],
                    order_id=order.id,
                    quantity=order.quantity - order.filled_quantity,
                    price=order.price,
                    asset_balance=asset_balance,
                ).model_dump()
            )

        oco_order: OCOOrder = self._oco_manager.create()
        order.set_oco_id(oco_order.id)
        oco_order.leg_a = order
        self._order_manager.append(order)
        payload["oco_id"] = order.oco_id

        is_crossable = (
            order.side == Side.BID
            and ob.best_ask is not None
            and payload["limit_price"] >= ob.best_ask
        ) or (
            order.side == Side.ASK
            and ob.best_bid is not None
            and payload["limit_price"] <= ob.best_bid
        )

        if payload["order_type"] == OrderType.LIMIT_OCO and not is_crossable:
            order.price = payload["limit_price"]
            ob.append(order, order.price)
            place_order_event(balance_manager.get_balance(payload["user_id"]))
            return

        result: MatchResult = self._match(order, ob)
        order.filled_quantity = result.quantity

        if result.quantity:
            order.filled_quantity = result.quantity
            payload["open_quantity"] = result.quantity
            payload["standing_quantity"] = order.quantity - result.quantity
            balance_manager.increase_balance(payload["user_id"], result.quantity)

        if result.outcome == MatchOutcome.SUCCESS:
            payload["status"] = OrderStatus.FILLED
        elif result.outcome == MatchOutcome.PARTIAL:
            payload["status"] = OrderStatus.PARTIALLY_FILLED

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
                    asset_balance=balance_manager.get_balance(payload["user_id"]),
                    metadata={"tag": order.tag},
                ).model_dump()
            )

        if result.outcome != MatchOutcome.SUCCESS:
            price = payload["limit_price"] or result.price or ob.price
            order.price = price
            ob.append(order, price)

            place_order_event(balance_manager.get_balance(payload["user_id"]))

        self._push_to_queue(payload)

    def _update_payload_quantities(
        self,
        order: SpotOrder,
        filled_quantity: int,
        payload: dict,
        balance_manager: BalanceManager,
    ) -> None:
        """
        Updates the open, standing quantity and total asset balance
        for an order and user.

        Args:
            order (SpotOrder): Order that got hit.
            filled_quantity (int): Quantity filled.
            payload (dict): Order payload for the `order`.
        """
        user_id = payload["user_id"]

        if order.tag in (Tag.STOP_LOSS, Tag.TAKE_PROFIT):
            payload["open_quantity"] -= filled_quantity
            balance_manager.decrease_balance(user_id, filled_quantity)
        elif order.side == Side.BID:
            payload["open_quantity"] += filled_quantity
            payload["standing_quantity"] -= filled_quantity
            balance_manager.increase_balance(user_id, filled_quantity)
        else:
            payload["open_quantity"] += filled_quantity
            payload["standing_quantity"] -= filled_quantity
            balance_manager.decrease_balance(user_id, filled_quantity)

    def _handle_filled_order(
        self,
        order: SpotOrder,
        filled_quantity: int,
        price: float,
        ob: OrderBook[SpotOrder],
    ) -> None:
        """Handle a resting order that was fully filled."""
        payload = self._order_payloads[order.id]
        _, balance_manager = self._orderbooks[payload["instrument"]]
        self._update_payload_quantities(
            order, filled_quantity, payload, balance_manager
        )
        asset_balance = balance_manager.get_balance(payload["user_id"])

        if order.tag == Tag.ENTRY:
            payload["status"] = OrderStatus.FILLED
            ob.remove(order, order.price)

            if order.oco_id is not None:
                oco_order = self._oco_manager.get(order.oco_id)
                if oco_order.leg_b is None and oco_order.leg_c is None:
                    self._place_tp_sl(oco_order, ob)
                else:
                    self._mutate_tp_sl(oco_order, payload["open_quantity"])
            else:
                balance_manager.remove(payload["user_id"])
                self._order_manager.remove(order.id)
        else:
            oco_order = self._oco_manager.get(order.oco_id)
            self._remove_tp_sl(oco_order, ob)
            if payload["open_quantity"] == 0 and payload["standing_quantity"] == 0:
                self._oco_manager.remove(oco_order.id)
                balance_manager.remove(payload["user_id"])
                self._order_manager.remove(order.id)
                payload["status"] = OrderStatus.CLOSED
            elif payload["status"] == OrderStatus.FILLED:
                payload["status"] = OrderStatus.CLOSED

        log_event.delay(
            Event(
                event_type=EventType.ORDER_FILLED,
                user_id=payload["user_id"],
                order_id=order.id,
                quantity=filled_quantity,
                price=price,
                asset_balance=asset_balance,
                metadata={"tag": order.tag},
            ).model_dump()
        )
        self._push_to_queue(payload)

    def _handle_touched_order(
        self,
        order: SpotOrder,
        touched_quantity: int,
        price: float,
        ob: OrderBook[SpotOrder],
    ) -> None:
        """Handle a resting order that was partially filled (touched)."""
        payload = self._order_payloads[order.id]
        _, balance_manager = self._orderbooks[payload["instrument"]]
        self._update_payload_quantities(
            order, touched_quantity, payload, balance_manager
        )

        if payload["status"] == OrderStatus.PENDING:
            payload["status"] = OrderStatus.PARTIALLY_FILLED
        elif payload["status"] == OrderStatus.FILLED:
            payload["status"] = OrderStatus.PARTIALLY_CLOSED

        if order.oco_id is not None:
            oco_order = self._oco_manager.get(order.oco_id)
            if oco_order.leg_b is None and oco_order.leg_c is None:
                self._place_tp_sl(oco_order, ob)
            else:
                self._mutate_tp_sl(oco_order, payload["open_quantity"])

        log_event.delay(
            Event(
                event_type=EventType.ORDER_PARTIALLY_FILLED,
                user_id=payload["user_id"],
                order_id=order.id,
                quantity=touched_quantity,
                price=price,
                asset_balance=balance_manager.get_balance(payload["user_id"]),
                metadata={"tag": order.tag.value},
            ).model_dump()
        )
        self._push_to_queue(payload)

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
        payload = self._order_payloads[entry_order.id]

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

    def _push_to_queue(self, payload: dict) -> None:
        self._payload_queue.append(
            PusherPayload(
                action=PusherPayloadTopic.UPDATE, table_cls="Orders", data=payload
            ).model_dump()
        )
