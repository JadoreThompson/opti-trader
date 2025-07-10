import asyncio

from datetime import datetime
from collections.abc import Iterable
from pprint import pprint
from typing import Callable

from config import FUTURES_QUEUE_KEY, PRODUCTION, REDIS_CLIENT
from enums import OrderStatus, OrderType, Side
from .base_engine import BaseEngine
from ..enums import Tag, MatchOutcome
from ..order import Order
from ..orderbook import OrderBook
from ..position import Position
from ..typing import (
    ClosePayloadQuantity,
    EnginePayloadCategory,
    MatchResult,
    ClosePayload,
    ModifyPayload,
)
from ..utils import (
    calc_sell_pnl,
    calc_buy_pnl,
    update_upl,
)


class FuturesEngine(BaseEngine):
    def __init__(
        self,
    ) -> None:
        super().__init__()

    async def _listen(self) -> None:
        """
        DO NOT CALL!!!

        Listens to the Redis pub/sub channel for incoming order-related messages
        and routes them to the appropriate handler.

        This method is asynchronous and should not be called directly.

        Raises:
            Any exceptions related to Redis connection or message parsing.
        """

        await asyncio.sleep(0)

        handlers: dict[EnginePayloadCategory, Callable] = {
            EnginePayloadCategory.NEW: self.place_order,
            EnginePayloadCategory.MODIFY: self.modify_position,
            EnginePayloadCategory.CLOSE: self.close_order,
            EnginePayloadCategory.CANCEL: self.cancel_order,
            EnginePayloadCategory.APPEND: self._handle_append_ob,
        }

        async with REDIS_CLIENT.pubsub() as ps:
            await ps.subscribe(FUTURES_QUEUE_KEY)
            async for message in ps.listen():
                if message["type"] == "subscribe":
                    continue

                # payload: EnginePayload = json.loads(message["data"])
                # handlers[payload["category"]](json.loads(payload["content"]))
                payload = message["data"]
                handlers[payload["category"]](payload["content"])

    def place_order(self, payload: dict) -> None:
        """
        Handles placement of a new order. Matches it against the orderbook if possible,
        and places it in the book otherwise. Also manages creation of related TP/SL orders.

        Args:
        payload (dict): The order data containing instrument, side, type, limit price, etc.
        """
        if payload["instrument"] not in self._order_books and not PRODUCTION:
            ob = self._order_books[payload["instrument"]] = OrderBook()

        if payload["instrument"] not in self._order_books:
            return

        ob = self._order_books[payload["instrument"]]
        # order = Order(payload, Tag.ENTRY, payload["side"])
        # self._position_manager.create(order)
        pos: Position = self._position_manager.create(payload)
        order: Order = pos.entry_order

        # Appending to book if we can't fill right now.
        if (
            payload["order_type"] == OrderType.LIMIT
            and (ob.best_bid if order.side == Side.ASK else ob.best_ask)
            != payload["limit_price"]
        ):
            ob.append(order, payload["limit_price"])
            # order.current_price_level = payload["limit_price"]
            return

        result: MatchResult = self._match(order, ob)

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            ob.set_price(result.price)
            self._place_tp_sl(pos.entry_order, ob)

            if result.outcome == MatchOutcome.SUCCESS:
                pos.set_filled()
                return

        price = result.price if result.price is not None else ob.price
        ob.append(pos.entry_order, price)
        order.current_price_level = price

        # if result.outcome == MatchOutcome.SUCCESS:
        #     # payload["status"] = OrderStatus.FILLED
        #     # payload["standing_quantity"] = payload[
        #     #     "quantity"
        #     # ]  # Resetting so we can match TP & SL.
        #     # payload["filled_price"] = result.price
        #     pos.set_filled()
        #     self._place_tp_sl(order, ob)
        # elif result.outcome == MatchOutcome.PARTIAL:
        #     ob.append(order, result.price)
        #     # payload["status"] = OrderStatus.PARTIALLY_FILLED
        #     # order.current_price_level = result.price
        # else:
        #     ob.append(order, ob.price)
        #     # order.current_price_level = ob.price

    # def close_order(self, data: ClosePayload) -> None:
    #     """
    #     Attempts to close a position by placing a market order in the opposite direction.
    #     Handles PnL calculation and status updates.

    #     Args:
    #         data (ClosePayload): Payload containing order ID and optional quantity to close.

    #     Raises:
    #         ValueError: If the order is not yet filled or partially filled.
    #     """

    #     order_id: str = data["order_id"]
    #     pos: Position = self._position_manager.get(order_id)
    #     entry_order: Order = pos.entry_order

    #     if entry_order.payload["status"] in (
    #         OrderStatus.PENDING,
    #         OrderStatus.PARTIALLY_FILLED,
    #     ):
    #         raise ValueError(
    #             f"Cannot close {entry_order.payload["status"]} order. Call cancel_order instead."
    #         )

    #     ob: OrderBook = self._order_books[pos.instrument]
    #     requested_qty = self._validate_close_payload_quantity(
    #         data["quantity"], entry_order.payload["standing_quantity"]
    #     )

    #     # Place opposing order and try to exit.
    #     dummy_order = Order(
    #         {
    #             "order_id": entry_order.payload["order_id"],
    #             "standing_quantity": requested_qty,
    #         },
    #         Tag.DUMMY,
    #         Side.ASK if entry_order.side == Side.BID else Side.BID,
    #     )

    #     result: MatchResult = self._match(dummy_order, ob)
    #     filled_qty = requested_qty - dummy_order.payload["standing_quantity"]
    #     calc_pnl_fn = calc_buy_pnl if entry_order.side == Side.BID else calc_sell_pnl

    #     if result.outcome == MatchOutcome.FAILURE:
    #         realised_pnl = 0.0
    #     else:
    #         realised_pnl = calc_pnl_fn(
    #             filled_qty * entry_order.payload["filled_price"],
    #             entry_order.payload["filled_price"],
    #             result.price,
    #         )

    #     if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
    #         ob.set_price(result.price)

    #     entry_order.payload["realised_pnl"] += realised_pnl

    #     if result.outcome == MatchOutcome.SUCCESS:
    #         if requested_qty == entry_order.payload["standing_quantity"]:
    #             self._collapse_position(entry_order.payload["order_id"], ob)

    #             entry_order.payload["status"] = OrderStatus.CLOSED
    #             entry_order.payload["closed_at"] = datetime.now()
    #             entry_order.payload["closed_price"] = result.price
    #             entry_order.payload["standing_quantity"] = 0
    #             entry_order.payload["unrealised_pnl"] = 0.0
    #             return

    #         entry_order.payload["status"] = OrderStatus.PARTIALLY_CLOSED
    #     elif result.outcome == MatchOutcome.PARTIAL:
    #         entry_order.payload["status"] = OrderStatus.PARTIALLY_CLOSED

    #     entry_order.payload["standing_quantity"] -= filled_qty
    #     if result.outcome == MatchOutcome.FAILURE:
    #         entry_order.payload["unrealised_pnl"] = calc_pnl_fn(
    #             entry_order.payload["standing_quantity"]
    #             * entry_order.payload["filled_price"],
    #             entry_order.payload["filled_price"],
    #             ob.price,
    #         )
    #     else:
    #         entry_order.payload["unrealised_pnl"] = calc_pnl_fn(
    #             entry_order.payload["standing_quantity"]
    #             * entry_order.payload["filled_price"],
    #             entry_order.payload["filled_price"],
    #             result.price,
    #         )
    def close_order(self, data: ClosePayload) -> None:
        """
        Attempts to close a position by placing a market order in the opposite direction.
        Handles PnL calculation and status updates.

        Args:
            data (ClosePayload): Payload containing order ID and optional quantity to close.

        Raises:
            ValueError: If the order is not yet filled or partially filled.
        """

        order_id: str = data["order_id"]
        pos: Position = self._position_manager.get(order_id)
        entry_order: Order = pos.entry_order

        if pos._payload["status"] == OrderStatus.PENDING:
            raise ValueError("Cannot close pending order. Call cancel_order instead.")

        ob: OrderBook = self._order_books[pos.instrument]
        requested_qty = self._validate_close_payload_quantity(
            data["quantity"],
            (
                pos.standing_quantity
                if pos._payload["status"]
                in (
                    OrderStatus.FILLED,
                    OrderStatus.PARTIALLY_CLOSED,
                    OrderStatus.CLOSED,
                )
                else pos.quantity - pos.standing_quantity
            ),
        )

        # Place opposing order and try to exit.
        dummy_pos = Position(
            {
                # "order_id": pos.id,
                # "standing_quantity": requested_qty,
                # "side": Side.ASK if pos._payload['side'] == Side.BID else Side.BID,
                # "instrument": pos.instrument,
                # 'status': OrderStatus.PENDING,
                # 'quantity'
                **pos._payload,
                "standing_quantity": requested_qty,
                "side": Side.ASK if pos._payload["side"] == Side.BID else Side.BID,
                "status": OrderStatus.PENDING,
            }
        )
        dummy_order = dummy_pos.entry_order

        result: MatchResult = self._match(dummy_order, ob)
        filled_qty = requested_qty - dummy_pos.standing_quantity

        # if result.outcome == MatchOutcome.FAILURE:
        #     realised_pnl = 0.0
        # else:
        #     realised_pnl = calc_pnl_fn(
        #         filled_qty * entry_order.payload["filled_price"],
        #         entry_order.payload["filled_price"],
        #         result.price,
        #     )

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            ob.set_price(result.price)

            pos_quantity = pos.standing_quantity
            pos.reduce_standing_quantity(result.price, filled_qty)
            pos.update_rpnl(result.price, filled_qty)

            if result.outcome == MatchOutcome.SUCCESS and requested_qty == pos_quantity:
                self._collapse_position(pos.id, ob)
                pos.set_closed(result.price)
                return

            pos._payload["status"] = OrderStatus.PARTIALLY_CLOSED

    def modify_position(self, data: ModifyPayload) -> None:
        """
        Handles the shuffling and value assignment of an existing
        position

        Args:
            data (ModifyPayload): Dictionary containing modification details.
        """
        pos = self._position_manager.get(data["order_id"])
        ob = self._order_books[pos.instrument]
        order = pos.entry_order
        payload = pos._payload
        status = payload["status"]

        # Handle limit price field
        if data["limit_price"] is not None:
            if (
                status == OrderStatus.PENDING
                and payload["order_type"] == OrderType.LIMIT
            ):
                ob.remove(order, payload["limit_price"])
                ob.append(order, data["limit_price"])
                payload["limit_price"] = data["limit_price"]
                order.current_price_level = data["limit_price"]
            else:
                raise ValueError(
                    f"Cannot change limit price. Order status must be {OrderStatus.PENDING} and order type {OrderType.LIMIT}"
                )

        # Handle TP & SL price
        if status not in (OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED):
            if data["take_profit"] != payload["take_profit"] and pos.take_profit_order:
                ob.remove(pos.take_profit_order, payload["take_profit"])
                payload["take_profit"] = data["take_profit"]
            if data["stop_loss"] != payload["stop_loss"] and pos.stop_loss_order:
                ob.remove(pos.stop_loss_order, payload["stop_loss"])
                payload["stop_loss"] = data["stop_loss"]

            self._place_tp_sl(order, ob)

    def cancel_order(self, data: ClosePayload) -> None:
        """
        Cancels a pending or partially filled order. Removes it from the orderbook
        and updates position/order status accordingly.

        Args:
            data (ClosePayload): Payload containing order ID and optional quantity.

        Raises:
            ValueError: If the order is not cancellable (not pending or partially filled).
        """

        pos = self._position_manager.get(data["order_id"])
        order = pos.entry_order
        ob = self._order_books[pos.instrument]
        payload = pos._payload

        # print(payload)

        if payload["status"] == OrderStatus.PENDING:
            ob.remove(order, payload["limit_price"] or order.current_price_level)
            self._position_manager.remove(payload["order_id"])

            payload["status"] = OrderStatus.CANCELLED
            payload["closed_at"] = datetime.now()
            return

        if payload["status"] == OrderStatus.PARTIALLY_FILLED:
            # print("HIHIHIHI")
            self._handle_partially_filled_order_cancel(
                pos,
                ob,
                self._validate_close_payload_quantity(
                    data["quantity"], payload["standing_quantity"]
                ),
            )
            return

        raise ValueError(
            f"Cannot cancel order with status {payload['status']}. Must have status '{OrderStatus.PENDING}' or '{OrderStatus.PARTIALLY_FILLED}'."
        )

    def _place_tp_sl(
        self, order: Order, ob: OrderBook, pos: Position | None = None
    ) -> None:
        """
        Places associated take profit and stop loss orders in the orderbook
        for a given filled entry order.

        Args:
            order (Order): The filled entry order.
            ob (OrderBook): The relevant orderbook.
            pos (Position, optional): The position associated with the order. If None, it is resolved internally.

        Raises:
            ValueError: If the order is not an entry order or if no position is found.
        """

        if order.tag != Tag.ENTRY:
            raise ValueError(
                f"Cannot place TP or SL order with order containing Tag {order.tag} must be an order with Tag.ENTRY"
            )
        if pos is None:
            pos = self._position_manager.get(order.position.id)

        if order.position.id == "36":
            pprint(locals())
        if pos is None:
            raise ValueError("Cannot place tp or sl without position.")

        exit_side = Side.ASK if order.side == Side.BID else Side.BID

        if pos._payload["take_profit"] is not None:
            pos.take_profit_order = Order(pos, Tag.TAKE_PROFIT, exit_side)
            ob.append(pos.take_profit_order, pos._payload["take_profit"])

        if pos._payload["stop_loss"] is not None:
            pos.stop_loss_order = Order(pos, Tag.STOP_LOSS, exit_side)
            ob.append(pos.stop_loss_order, pos._payload["stop_loss"])

    def _handle_filled_orders(
        self, orders: Iterable[tuple[Order, int]], price: float, ob: OrderBook
    ) -> None:
        """
        Handles cleanup and status updates for a set of filled orders after a match.
        Also calculates and pushes PnL updates for each order.

        Args:
            orders (Iterable[tuple[Order, int]]): A list of (order, filled quantity) tuples.
            price (float): The price at which the orders were filled.
            ob (OrderBook): The relevant orderbook.
        """

        for order, filled_quantity in orders:
            ob.remove(order, price)

            if order.position.id == "36":
                print("REMOVED FROM OB")

            if order.tag == Tag.ENTRY:
                if order.position.id == "36":
                    print("IM STILL HERE")
                self._place_tp_sl(order, ob)
                order.position.set_filled()
            else:
                pos = self._position_manager.get(order.position.id)
                self._collapse_exit_orders(order, ob, pos)
                self._position_manager.remove(order.position.id)

                order.position.update_rpnl(price, filled_quantity)
                order.position.set_closed(price)

    def _handle_touched_orders(
        self,
        orders: Iterable[tuple[Order, int]],
        # filled_orders: list[tuple[Order, int]],
        price: float,
    ) -> None:
        """
        Handles updates for orders that were touched (partially filled or nearly matched).
        Updates their statuses and PnLs accordingly.

        Args:
            orders (Iterable[tuple[Order, int]]): Orders touched in the matching process.
            filled_orders (list[tuple[Order, int]]): Orders that should be processed as filled after this step.
            price (float): The market price that touched the orders.
        """

        # for order, standing_qty in orders:
        for order in orders:
            if order.tag in (Tag.STOP_LOSS, Tag.TAKE_PROFIT):
                order.position.update_upnl(price)

    def _handle_partially_filled_order_cancel(
        self, pos: Position, ob: OrderBook, requested_qty: int
    ) -> None:
        """
        Handles the cancellation of a partially filled order by reducing its standing quantity.
        If the order is effectively filled through cancellation, it is marked as such and processed.

        Args:
            pos (Position): The position associated with the order.
            ob (OrderBook): The orderbook containing the order.
            requested_qty (int): Quantity requested to cancel.
        """
        order: Order = pos.entry_order
        payload = pos._payload
        # order.payload["standing_quantity"] -= requested_qty
        # order.payload["quantity"] -= requested_qty
        # payload["standing_quantity"] -= requested_qty
        # if order.payload["standing_quantity"] == 0:

        if payload["standing_quantity"] - requested_qty == 0:
            # order.payload["status"] = OrderStatus.FILLED
            # order.payload["filled_price"] = order.current_price_level
            # order.payload["standing_quantity"] = order.payload[
            #     "quantity"
            # ]  # Re-assigning so TP & SL can be matched against.
            # pos.set_filled()
            pos.set_filled_by_cancel()
            ob.remove(order, payload["limit_price"] or order.current_price_level)
            self._place_tp_sl(order, ob, pos)
            order.current_price_level = None

    def _collapse_position(
        self, order_id: str, ob: OrderBook | None = None, pos: Position | None = None
    ) -> None:
        """
        Removes all related orders (entry, stop loss, take profit) from the orderbook
        and deletes the position from the position manager.

        Args:
            order_id (str): The ID of the order associated with the position.
            ob (OrderBook, optional): The orderbook to use. If None, it is resolved internally.
            pos (Position, optional): The position to collapse. If None, it is resolved from the position manager.
        """
        pos: Position | None = self._position_manager.get(order_id)

        if ob is None:
            ob = self._order_books[pos.instrument]

        order = pos.entry_order

        if (
            order
            and order.current_price_level
            and pos._payload["status"]
            in (
                OrderStatus.PENDING,
                OrderStatus.PARTIALLY_FILLED,
            )
        ):
            ob.remove(order, order.current_price_level)

        if pos.take_profit_order is not None:
            ob.remove(pos.take_profit_order, pos._payload["take_profit"])
            # pos.take_profit_order = None

        if pos.stop_loss_order is not None:
            ob.remove(pos.stop_loss_order, pos._payload["stop_loss"])
            # pos.stop_loss_order = None

        self._position_manager.remove(order_id)

    def _collapse_exit_orders(
        self, order: Order, ob: OrderBook, pos: Position | None = None
    ):
        """
        Removes stop loss and take profit orders from the orderbook and disassociates
        them from the given position.

        Args:
            order (Order): The exit order (take profit or stop loss).
            ob (OrderBook): The orderbook where the order resides.
            pos (Position | None, optional): The related position. If None, it is resolved internally.

        Raises:
            ValueError: If the order is an entry order (Tag.ENTRY).
        """
        if order.tag == Tag.ENTRY:
            raise ValueError("Cannot be called with order that has Tag.ENTRY.")

        if pos is None:
            pos = self._position_manager.get(order.payload["order_id"])

        if pos.take_profit_order and pos.take_profit_order is not order:
            ob.remove(pos.take_profit_order, pos._payload["take_profit"])
            pos.take_profit_order = None
        if pos.stop_loss_order and pos.stop_loss_order is not order:
            ob.remove(pos.stop_loss_order, pos._payload["stop_loss"])
            pos.stop_loss_order = None

    def _validate_close_payload_quantity(
        self, quantity: ClosePayloadQuantity, filled_quantity: int
    ) -> int:
        try:
            if quantity == "ALL":
                return filled_quantity

            quantity = int(quantity)
            # if quantity <= filled_quantity:
            #     return quantity
            return min(filled_quantity, quantity)
        except TypeError:
            pass

        raise ValueError("Invalid quantity.")

    def _handle_append_ob(self, data: dict) -> None:
        """
        Initializes a new orderbook for an instrument if it does not exist.

        Args:
            data (dict): Data containing the instrument and optional initial price.
        """

        if data["instrument"] not in self._order_books:
            self._order_books[data["instrument"]] = OrderBook(data["price"])
