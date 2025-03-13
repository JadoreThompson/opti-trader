import asyncio
import json
import inspect

from datetime import datetime
from collections.abc import Iterable
from r_mutex import Lock
from typing import Callable, TypedDict

from config import FUTURES_QUEUE_KEY, REDIS_CLIENT
from enums import OrderStatus, OrderType, Side
from .base_engine import BaseEngine
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
    MatchResult,
)


class CloseOrderPayload(TypedDict):
    order_id: str
    instrument: str
    price: float


class FuturesEngine(BaseEngine):
    def __init__(
        self,
        instrument_lock: Lock,
        pusher: Pusher,
    ) -> None:
        super().__init__(instrument_lock, pusher)

    async def _listen(self) -> None:
        """
        Listens to the pubsub channel for incoming orders and
        delegates them to appropriate handlers.
        """
        await asyncio.sleep(0)

        handlers: dict[EnginePayloadCategory, Callable] = {
            EnginePayloadCategory.NEW: self._handle_new,
            EnginePayloadCategory.MODIFY: self._handle_modify,
            EnginePayloadCategory.CLOSE: self._handle_close,
        }

        async with REDIS_CLIENT.pubsub() as ps:
            await ps.subscribe(FUTURES_QUEUE_KEY)
            async for message in ps.listen():
                if message["type"] == "subscribe":
                    continue

                payload: EnginePayload = json.loads(message["data"])
                func = handlers[payload["category"]](json.loads(payload["content"]))
                
                if inspect.iscoroutine(func):
                    await func

    async def _handle_new(self, payload: dict) -> None:
        """
        Handles the result of a new order by matching it against the order book.
        Depending on the order type (market or limit), the order is either matched
        immediately or added to the order book for future matching.

        If the order is filled, take profit and stop loss orders are placed if applicable.

        Args:
            payload (dict): The order data, including order type, side, price, and quantity.
        """
        instrument: str = payload["instrument"]

        ob = self._order_books.get(
            instrument,
            OrderBook(
                instrument,
                self.instrument_lock,
                float((await REDIS_CLIENT.get(f"{instrument}.price")).decode()),
                self.pusher,
            ),
        )
        order = Order(payload, Tag.ENTRY, payload["side"])

        func: dict[OrderType, callable] = {
            OrderType.MARKET: self._handle_market_order,
            OrderType.LIMIT: self._handle_limit_order,
        }[payload["order_type"]]

        result: MatchResult = func(order, ob)

        if payload["order_type"] == OrderType.LIMIT:
            return

        if result.outcome == 2:
            ob.set_price(result.price)
            payload["status"] = OrderStatus.FILLED
            payload["standing_quantity"] = payload["quantity"]
            payload["filled_price"] = result.price
            self._place_tp_sl(order, ob)
        else:
            ob.append(order, payload["price"])
            if payload["standing_quantity"] != payload["quantity"]:
                payload["status"] = OrderStatus.PARTIALLY_FILLED

        self.pusher.append(payload)

    def _handle_market_order(self, order: Order, ob: OrderBook) -> MatchResult:
        return self._match(
            order.payload,
            order.payload["side"],
            ob,
            order.payload["price"],
            20,
        )

    def _handle_limit_order(self, order: Order, ob: OrderBook) -> None:
        ob.append(order, order.payload["limit_price"])

    def _match(
        self,
        order: dict,
        order_side: Side,
        ob: OrderBook,
        price: float,
        max_attempts: int = 5,
        attempt: int = 0,
    ) -> MatchResult:
        """
        Matches order against opposing book

        Args:
            order (dict)
            order_side (Side)
            ob (Orderbook): orderbook
            price (float): price to target
            max_attempts (int, optional): Defaults to 5.
            attempt (int, optional): Defaults to 0.

        Returns:
            MatchResult:
                Filled: (2, price)
                Partially filled: (1, None)
                Not filled: (0, None)
        """
        touched: list[Order] = []
        filled: list[tuple[Order, int]] = []
        book = "asks" if order_side == Side.BUY else "bids"
        target_price = ob.best_price(book, price)

        if target_price is None:
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
            self._match(order, order_side, ob, target_price, max_attempts, attempt)

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
            ob.append(
                Order(
                    order.payload,
                    Tag.TAKE_PROFIT,
                    Side.SELL if order.payload["side"] == Side.BUY else Side.BUY,
                ),
                order.payload["take_profit"],
            )

        if order.payload["stop_loss"] is not None:
            ob.append(
                Order(
                    order.payload,
                    Tag.STOP_LOSS,
                    Side.SELL if order.payload["side"] == Side.BUY else Side.BUY,
                ),
                order.payload["stop_loss"],
            )

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
                continue
            if order.payload["status"] == OrderStatus.CLOSED:
                self.pusher.append(
                    {
                        "user_id": order.payload["user_id"],
                        "amount": order.payload["realised_pnl"],
                    },
                    "balance",
                )

            self.pusher.append(order.payload)

    def _handle_close(self, payload: CloseOrderPayload) -> None:
        """
        Handles the result from attempting to match the order
        in order to close it

        Args:
            payload (dict)
        """
        ob = self._order_books[payload["instrument"]]

        try:
            pos = ob.get(payload["order_id"])
        except PositionNotFound:
            return

        ob.remove_all(pos.order)
        before_standing_quantity: int = pos.order.payload["standing_quantity"]
        result: MatchResult = self._match(
            pos.order.payload,
            Side.SELL if pos.order.payload["side"] == Side.BUY else Side.SELL,
            ob,
            payload["price"],
        )

        if result.outcome == 2:
            ob.set_price(result.price)
            pos.order.payload["status"] = OrderStatus.CLOSED
            pos.order.payload["closed_at"] = datetime.now()
            pos_value: float = (
                before_standing_quantity * pos.order.payload["filled_price"]
            )
            calc_pl_fn = (
                calc_buy_pl if pos.order.payload["side"] == Side.BUY else calc_sell_pl
            )
            pos.order.payload["realised_pnl"] += calc_pl_fn(
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
