import asyncio

from datetime import datetime
from collections.abc import Iterable
from r_mutex import LockClient
from typing import Callable

from config import FUTURES_QUEUE_KEY, PRODUCTION, REDIS_CLIENT
from enums import OrderStatus, OrderType, Side
from .base_engine import BaseEngine
from ..enums import Tag, MatchOutcome
from ..order import Order
from ..orderbook import OrderBook
from ..position import Position
from ..pusher import Pusher
from ..typing import (
    ClosePayloadQuantity,
    EnginePayloadCategory,
    MatchResult,
    ClosePayload,
)
from ..utils import (
    calc_sell_pnl,
    calc_buy_pnl,
    update_upl,
)


class FuturesEngine(BaseEngine):
    def __init__(
        self,
        instrument_lock: LockClient,
        pusher: Pusher,
    ) -> None:
        super().__init__(instrument_lock, pusher)

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
            EnginePayloadCategory.CANCEL: self._handle_cancel,
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
        order = Order(payload, Tag.ENTRY, payload["side"])
        self._position_manager.create(order)

        # Appending to book if we can't fill right now.
        if (
            payload["order_type"] == OrderType.LIMIT
            and (ob.best_bid if order.side == Side.ASK else ob.best_ask)
            != payload["limit_price"]
        ):
            ob.append(order, payload["limit_price"])
            order.current_price_level = payload["limit_price"]
            return

        result: MatchResult = self._match(order, ob)

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            ob.set_price(result.price)

        if result.outcome == MatchOutcome.SUCCESS:
            payload["status"] = OrderStatus.FILLED
            payload["standing_quantity"] = payload[
                "quantity"
            ]  # Resetting so we can match TP & SL.
            payload["filled_price"] = result.price
            self._place_tp_sl(order, ob)
        elif result.outcome == MatchOutcome.PARTIAL:
            ob.append(order, result.price)
            payload["status"] = OrderStatus.PARTIALLY_FILLED
            order.current_price_level = result.price
        else:
            ob.append(order, ob.price)
            order.current_price_level = ob.price

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

        if entry_order.payload["status"] in (
            OrderStatus.PENDING,
            OrderStatus.PARTIALLY_FILLED,
        ):
            raise ValueError(
                f"Cannot close {entry_order.payload["status"]} order. Call cancel_order instead."
            )

        ob: OrderBook = self._order_books[pos.instrument]
        requested_qty = self._validate_close_payload_quantity(
            data["quantity"], entry_order.payload["standing_quantity"]
        )

        # Place opposing order and try to exit.
        dummy_order = Order(
            {
                "order_id": entry_order.payload["order_id"],
                "standing_quantity": requested_qty,
            },
            Tag.DUMMY,
            Side.ASK if entry_order.side == Side.BID else Side.BID,
        )

        result: MatchResult = self._match(dummy_order, ob)
        filled_qty = requested_qty - dummy_order.payload["standing_quantity"]
        calc_pnl_fn = calc_buy_pnl if entry_order.side == Side.BID else calc_sell_pnl

        if result.outcome == MatchOutcome.FAILURE:
            realised_pnl = 0.0
        else:
            realised_pnl = calc_pnl_fn(
                filled_qty * entry_order.payload["filled_price"],
                entry_order.payload["filled_price"],
                result.price,
            )

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            ob.set_price(result.price)

        entry_order.payload["realised_pnl"] += realised_pnl

        if result.outcome == MatchOutcome.SUCCESS:
            if requested_qty == entry_order.payload["standing_quantity"]:
                self._collapse_position(entry_order.payload["order_id"], ob)

                entry_order.payload["status"] = OrderStatus.CLOSED
                entry_order.payload["closed_at"] = datetime.now()
                entry_order.payload["closed_price"] = result.price
                entry_order.payload["standing_quantity"] = 0
                entry_order.payload["unrealised_pnl"] = 0.0
                return

            entry_order.payload["status"] = OrderStatus.PARTIALLY_CLOSED
        elif result.outcome == MatchOutcome.PARTIAL:
            entry_order.payload["status"] = OrderStatus.PARTIALLY_CLOSED

        entry_order.payload["standing_quantity"] -= filled_qty
        if result.outcome == MatchOutcome.FAILURE:
            entry_order.payload["unrealised_pnl"] = calc_pnl_fn(
                entry_order.payload["standing_quantity"]
                * entry_order.payload["filled_price"],
                entry_order.payload["filled_price"],
                ob.price,
            )
        else:
            entry_order.payload["unrealised_pnl"] = calc_pnl_fn(
                entry_order.payload["standing_quantity"]
                * entry_order.payload["filled_price"],
                entry_order.payload["filled_price"],
                result.price,
            )

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

        if order.payload["status"] == OrderStatus.PENDING:
            ob.remove(order, order.current_price_level)
            self._position_manager.remove(order.payload["order_id"])

            order.payload["status"] = OrderStatus.CANCELLED
            order.payload["closed_at"] = datetime.now()
            return

        if order.payload["status"] == OrderStatus.PARTIALLY_FILLED:
            self._handle_partially_filled_order_cancel(
                pos,
                ob,
                self._validate_close_payload_quantity(
                    data["quantity"], order.payload["standing_quantity"]
                ),
            )
            return

        raise ValueError(
            f"Cannot cancel order with status {order.payload['status']}. Must have status '{OrderStatus.PENDING}' or '{OrderStatus.PARTIALLY_FILLED}'."
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
            pos = self._position_manager.get(order.payload["order_id"])
        if pos is None:
            raise ValueError("Cannot place tp or sl without position.")

        if order.payload["take_profit"] is not None:
            pos.take_profit_order = Order(
                order.payload,
                Tag.TAKE_PROFIT,
                Side.ASK if order.side == Side.BID else Side.BID,
            )
            ob.append(pos.take_profit_order, order.payload["take_profit"])

        if order.payload["stop_loss"] is not None:
            pos.stop_loss_order = Order(
                order.payload,
                Tag.STOP_LOSS,
                Side.ASK if order.side == Side.BID else Side.BID,
            )
            ob.append(pos.stop_loss_order, order.payload["stop_loss"])

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

        for order, standing_quantity in orders:
            ob.remove(order, price)

            if order.tag == Tag.ENTRY:
                order.payload["status"] = OrderStatus.FILLED
                order.payload["standing_quantity"] = order.payload["quantity"]
                order.payload["filled_price"] = price
                order.last_touched_price = None
                order.current_price_level = None
                self._place_tp_sl(order, ob)
                update_upl(order, price)
            else:
                # Collapsing exit orders
                pos = self._position_manager.get(order.payload["order_id"])
                self._collapse_exit_orders(order, ob, pos)

                self._position_manager.remove(order.payload["order_id"])

                order.payload["status"] = OrderStatus.CLOSED
                order.payload["closed_at"] = datetime.now()
                order.payload["unrealised_pnl"] = 0.0
                order.payload["standing_quantity"] = 0
                order.payload["closed_price"] = price

                if order.payload["side"] == Side.BID:
                    order.payload["realised_pnl"] += calc_buy_pnl(
                        order.payload["filled_price"] * standing_quantity,
                        order.payload["filled_price"],
                        price,
                    )
                else:
                    order.payload["realised_pnl"] += calc_sell_pnl(
                        order.payload["filled_price"] * standing_quantity,
                        order.payload["filled_price"],
                        price,
                    )

            self.pusher.append(
                {
                    "user_id": order.payload["user_id"],
                    "amount": order.payload["realised_pnl"],
                },
                "balance",
            )

            self.pusher.append(order.payload)

    def _handle_touched_orders(
        self,
        orders: Iterable[tuple[Order, int]],
        filled_orders: list[tuple[Order, int]],
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

        for order, standing_qty in orders:
            order.last_touched_price = price

            if order.tag == Tag.ENTRY:
                order.payload["status"] = OrderStatus.PARTIALLY_FILLED
            else:
                order.payload["status"] = OrderStatus.PARTIALLY_CLOSED

                update_upl(order, price)
                if order.payload["status"] == OrderStatus.CLOSED:
                    filled_orders.append((order, standing_qty))

                self.pusher.append(
                    {
                        "user_id": order.payload["user_id"],
                        "amount": order.payload["realised_pnl"],
                    },
                    "balance",
                )

            self.pusher.append(order.payload)

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
        order.payload["standing_quantity"] -= requested_qty
        order.payload["quantity"] -= requested_qty

        if order.payload["standing_quantity"] == 0:
            order.payload["status"] = OrderStatus.FILLED
            order.payload["filled_price"] = order.current_price_level
            order.payload["standing_quantity"] = order.payload[
                "quantity"
            ]  # Re-assigning so TP & SL can be matched against.

            ob.remove(order, order.current_price_level)
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
        payload = pos.entry_order.payload

        if (
            payload["status"]
            in (
                OrderStatus.PENDING,
                OrderStatus.PARTIALLY_FILLED,
            )
            and order.current_price_level
        ):
            ob.remove(order, order.current_price_level)

        if pos.take_profit_order:
            ob.remove(pos.take_profit_order, order.payload["take_profit"])
            pos.take_profit_order = None

        if pos.stop_loss_order:
            ob.remove(pos.stop_loss_order, order.payload["stop_loss"])
            pos.stop_loss_order = None

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
            ob.remove(pos.take_profit_order, order.payload["take_profit"])
            pos.take_profit_order = None
        if pos.stop_loss_order and pos.stop_loss_order is not order:
            ob.remove(pos.stop_loss_order, order.payload["stop_loss"])
            pos.stop_loss_order = None

    def _validate_close_payload_quantity(
        self, quantity: ClosePayloadQuantity, standing_quantity: int
    ) -> int:
        """
        Validates and resolves the close quantity, allowing for 'ALL' as a special case.

        Args:
            quantity (ClosePayloadQuantity): Requested quantity to close.
            standing_quantity (int): The current standing quantity of the order.

        Returns:
            int: Validated integer quantity to close.

        Raises:
            ValueError: If the quantity is invalid or exceeds the standing quantity.
        """

        try:
            if quantity == "ALL":
                return standing_quantity

            quantity = int(quantity)
            if quantity <= standing_quantity:
                return quantity
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
