import asyncio
import multiprocessing
import warnings
import queue

from datetime import datetime
from collections import namedtuple
from collections.abc import Iterable
from r_mutex import Lock
from typing import Callable

from enums import OrderStatus, OrderType, Side
from .enums import Tag
from .exceptions import PositionNotFound
from .order import Order
from .orderbook import OrderBook
from .pusher import Pusher
from .utils import (
    EnginePayloadCategory,
    EnginePayload,
    calc_sell_pl,
    calc_buy_pl,
    calculate_upl,
)


MatchResult = namedtuple(
    "MatchResult",
    (
        "outcome",
        "price",
    ),
)


class FuturesEngine:
    def __init__(
        self,
        order_lock: Lock,
        instrument_lock: Lock,
        pusher: Pusher,
        queue: multiprocessing.Queue,
    ) -> None:
        self.pusher = pusher
        self.order_lock = order_lock
        self.instrument_lock = instrument_lock
        self.queue = queue

    async def run(self):
        """
        Initializes the engine and starts the pusher.

        This method sets up the connection to the pusher and waits for it to start.

        Raises:
            RuntimeError: Pusher failed to connect within 210 seconds
        """

        asyncio.create_task(self.pusher.run())

        i = 0
        while i < 20:
            if self.pusher.is_running:
                break
            i += 1
            m = f"Waiting for pusher - Sleeping for {i} seconds"
            warnings.warn(m)
            await asyncio.sleep(i)

        if i == 20:
            raise RuntimeError("Failed to connect to pusher")

        self._order_books: dict[str, OrderBook] = {
            "BTCUSD": OrderBook("BTCUSD", self.instrument_lock, 37, self.pusher),
        }

        await self._listen()

    async def _listen(self) -> None:
        """Listens to the message queue for incoming orders and delegates them to appropriate handlers."""
        await asyncio.sleep(0)

        handlers: dict[EnginePayloadCategory, Callable] = {
            EnginePayloadCategory.NEW: self._handle_new,
            EnginePayloadCategory.MODIFY: self._handle_modify,
            EnginePayloadCategory.CLOSE: self._handle_close,
        }

        while True:
            try:
                message: EnginePayload = self.queue.get_nowait()
                handlers[message["category"]](message["content"])
            except queue.Empty:
                pass
            await asyncio.sleep(0.2)

    def _handle_new(self, order_data: dict):
        """
        Handles the result of a new order by matching it against the order book.
        Depending on the order type (market or limit), the order is either matched immediately
        or added to the order book for future matching. If the order is filled, take profit and
        stop loss orders are placed if applicable.

        Args:
            order_data (dict): The order data, including order type, side, price, and quantity.
        """
        ob = self._order_books[order_data["instrument"]]
        order = Order(order_data, Tag.ENTRY, order_data["side"])

        func: dict[OrderType, callable] = {
            OrderType.MARKET: self._handle_market,
            OrderType.LIMIT: self._handle_limit,
        }[order_data["order_type"]]

        result: MatchResult = func(order, ob)

        if order_data["order_type"] == OrderType.LIMIT:
            return

        if result.outcome == 2:
            ob.set_price(result.price)
            order_data["status"] = OrderStatus.FILLED
            order_data["standing_quantity"] = order_data["quantity"]
            order_data["filled_price"] = result.price
            self._place_tp_sl(order, ob)
        else:
            ob.append(order, order_data["price"])
            if order_data["standing_quantity"] != order_data["quantity"]:
                order_data["status"] = OrderStatus.PARTIALLY_FILLED

        self.pusher.append(order_data)

    def _handle_market(self, order: Order, ob: OrderBook):
        return self._match(order.payload, ob, order.payload["price"], 20)

    def _handle_limit(self, order: Order, ob: OrderBook) -> None:
        ob.append(order, order.payload["limit_price"])

    def _match(
        self,
        order: dict,
        ob: OrderBook,
        price: float,
        max_attempts: int = 5,
        attempt: int = 0,
    ) -> MatchResult:
        """Matches order against opposing book
        -- Recursive

        Args:
            order (dict)
            ob (Orderbook): orderbook
            price (float): price to target
            max_attempts (int, optional): . Defaults to 5.
            attempt (int, optional): _description_. Defaults to 0.

        Returns:
            MatchResult:
                Filled: (2, price)
                Partially filled: (1, None)
                Not filled: (0, None)
        """
        touched: list[Order] = []
        filled: list[tuple[Order, int]] = []
        book = "bids" if order["side"] == Side.BUY else "asks"
        target_price = ob.best_price(book, price)

        if target_price is None:
            return MatchResult(0, None)

        if target_price not in ob[book]:
            return MatchResult(0, None)

        for existing_order in ob[book][target_price]:
            leftover_quant = (
                existing_order.payload["standing_quantity"] - order["standing_quantity"]
            )

            if leftover_quant >= 0:
                touched.append(existing_order)
                existing_order.payload["standing_quantity"] -= order[
                    "standing_quantity"
                ]
                order["standing_quantity"] = 0

            else:
                filled.append(
                    (existing_order, existing_order.payload["standing_quantity"])
                )
                order["standing_quantity"] -= existing_order.payload[
                    "standing_quantity"
                ]
                existing_order.payload["standing_quantity"] = 0

            if order["standing_quantity"] == 0:
                break

        if touched or filled:
            ob.set_price(price)

        self._handle_touched_orders(touched, target_price, ob, filled)
        self._handle_filled_orders(filled, ob, target_price)

        if order["standing_quantity"] == 0:
            return MatchResult(2, target_price)

        if attempt != max_attempts:
            attempt += 1
            self._match(order, ob, target_price, max_attempts, attempt)

        return MatchResult(1, None)

    def _place_tp_sl(self, order: Order, ob: OrderBook) -> None:
        """
        Handles the submission of an orders take profit and stop loss
        to the orderbook. Must only be called for orders that are filled

        Args:
            order (Order)
            ob (OrderBook)
        """
        ob.track(order)

        if order.payload["take_profit"] is not None:
            tp_order = Order(
                order.payload,
                Tag.TAKE_PROFIT,
                Side.SELL if order.payload["side"] == Side.BUY else Side.BUY,
            )
            ob.append(tp_order, order.payload["take_profit"])

        if order.payload["stop_loss"] is not None:
            sl_order = Order(
                order.payload,
                Tag.STOP_LOSS,
                Side.SELL if order.payload["side"] == Side.BUY else Side.BUY,
            )
            ob.append(sl_order, order.payload["stop_loss"])

    def _handle_filled_orders(
        self, orders: Iterable[tuple[Order, int]], ob: OrderBook, price: float
    ) -> None:
        """
        Handles the assigning of new order status', pnls and closure details
        for all orders that were filled during matching process. Each order within
        the iterable must have a standing quantity of 0 given to it by the match fucntion

        Args:
            orders (Iterable[tuple[Order, int]])
            ob (OrderBook)
            price (float)
        """
        for order, standing_quantity in orders:
            ob.remove(order)

            if order.tag == Tag.ENTRY:
                order.payload["status"] = OrderStatus.FILLED
                order.payload["standing_quantity"] = order.payload["quantity"]
                order.payload["filled_price"] = price
                self._place_tp_sl(order, ob)
            else:
                ob.remove_all(order)
                order.payload["status"] = OrderStatus.CLOSED
                order.payload["closed_at"] = datetime.now()
                order.payload["unrealised_pnl"] = order.payload["standing_quantity"] = (
                    0.0
                )
                order.payload["closed_price"] = price

                if order.payload["side"] == Side.BUY:
                    order.payload["realised_pnl"] += calc_buy_pl(
                        order.payload["filled_price"] * standing_quantity,
                        order.payload["filled_price"],
                        price,
                    )
                else:
                    order.payload["realised_pnl"] += calc_sell_pl(
                        order.payload["filled_price"] * standing_quantity,
                        order.payload["filled_price"],
                        price,
                    )

            if order.payload["status"] == OrderStatus.FILLED:
                calculate_upl(order, price, ob)
            else:
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
        orders: Iterable[Order],
        price: float,
        ob: OrderBook,
        filled_orders: list[tuple[Order, int]],
    ) -> None:
        """
        Handles the assigning of new order status', pnls and closure details
        for all orders that were touched during matching processed

        Args:
            orders (Iterable[Order])
            price (float)
            ob (OrderBook)
            filled_orders (list[tuple[Order, int]])
        """
        for order in orders:
            if order.tag == Tag.ENTRY:
                if order.payload["standing_quantity"] > 0:
                    order.payload["status"] = OrderStatus.PARTIALLY_FILLED
                else:
                    filled_orders.append((order, order.payload["standing_quantity"]))
                continue
            else:
                order.payload["status"] = OrderStatus.PARTIALLY_CLOSED

            calculate_upl(order, price, ob)

            if order.payload["status"] == OrderStatus.FILLED:
                filled_orders.append(order)
            if order.payload["status"] == OrderStatus.CLOSED:
                self.pusher.append(
                    {
                        "user_id": order.payload["user_id"],
                        "amount": order.payload["realised_pnl"],
                    },
                    "balance",
                )

            self.pusher.append(order.payload)

    def _handle_modify(self, order_data: dict) -> None:
        """
        Handles the reassignment of values to an order within the orderbook

        Args:
            order_data (dict)
        """
        try:
            pos = self._order_books[order_data["instrument"]].get(
                order_data["order_id"]
            )

            if pos.order.payload["status"] == OrderStatus.PENDING:
                if order_data["limit_price"] is not None:
                    pos.order.payload["limit_price"] = order_data["limit"]

            if (
                pos.order.payload["status"] != OrderStatus.PARTIALLY_CLOSED
                and pos.order.payload["status"] != OrderStatus.CLOSED
            ):
                if order_data["take_profit"] is not None:
                    pos.order.payload["take_profit"] = order_data["take_profit"]
                if order_data["stop_loss"] is not None:
                    pos.order.payload["stop_loss"] = order_data["stop_loss"]

            self.pusher.append(pos.order.payload)
        except PositionNotFound:
            pass

    def _handle_close(self, payload: dict) -> None:
        """
        Handles the result from attempting to match the order
        in order to close it

        Args:
            payload (dict)
        """
        try:
            ob = self._order_books[payload["instrument"]]
            pos = ob.get(payload["order_id"])
            ob.remove_all(pos.order)
            before_standing_quantity: int = pos.order.payload["standing_quantity"]
            result: MatchResult = self._match(pos.order.payload, ob, payload["price"])

            if result.outcome == 2:
                ob.set_price(result.price)
                pos.order.payload["status"] = OrderStatus.CLOSED
                pos.order.payload["closed_at"] = datetime.now()
                pos_value: float = (
                    before_standing_quantity * pos.order.payload["filled_price"],
                )

                if pos.order.payload["side"] == Side.BUY:
                    pos.order.payload["realised_pnl"] += calc_buy_pl(
                        pos_value,
                        pos.order.payload["filled_price"],
                        result.price,
                    )
                else:
                    pos.order.payload["realised_pnl"] += calc_sell_pl(
                        pos_value,
                        pos.order.payload["filled_price"],
                        result.price,
                    )

                pos.order.payload["standing_quantity"] = pos.order.payload[
                    "unrealised_pnl"
                ] = 0.0
                self.pusher.append(pos.order.payload, speed="fast")
                self.pusher.append(
                    {
                        "user_id": pos.order.payload["user_id"],
                        "amount": pos.order.payload["realised_pnl"],
                    }
                )
            else:
                new_pos = ob.append(pos.order, payload["price"])

                if pos.take_profit is not None:
                    ob.append(pos.take_profit, payload["price"])
                if pos.stop_loss is not None:
                    ob.append(pos.stop_loss, payload["price"])

                if (
                    new_pos.order.payload["standing_quantity"]
                    != new_pos.order.payload["quantity"]
                ):
                    new_pos.order.payload["status"] = OrderStatus.PARTIALLY_CLOSED

                self.pusher.append(new_pos.order.payload)
        except PositionNotFound:
            pass
