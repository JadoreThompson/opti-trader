import asyncio
import json

from datetime import datetime
from collections.abc import Iterable
from r_mutex import Lock
from typing import Callable

from config import SPOT_QUEUE_KEY, REDIS_CLIENT
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


class SpotEngine(BaseEngine):
    def __init__(self, instrument_lock: Lock, pusher: Pusher) -> None:
        super().__init__(instrument_lock, pusher)

    async def _listen(self) -> None:
        """Listens to the pubsub channel for incoming orders and delegates them to appropriate handlers."""
        await asyncio.sleep(0)

        handlers: dict[EnginePayloadCategory, Callable] = {
            EnginePayloadCategory.NEW: self._handle_new,
            EnginePayloadCategory.MODIFY: self._handle_modify,
            EnginePayloadCategory.CLOSE: self._handle_close,
        }

        async with REDIS_CLIENT.pubsub() as ps:
            await ps.subscribe(SPOT_QUEUE_KEY)
            async for message in ps.listen():
                if message["type"] == "subscribe":
                    continue

                payload: EnginePayload = json.loads(message["data"])
                handlers[payload["category"]](json.loads(payload["content"]))

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

        # self._handle_touched_orders(touched, target_price, ob, filled)
        # self._handle_filled_orders(filled, ob, target_price)

        if order["standing_quantity"] == 0:
            return MatchResult(2, target_price)

        if attempt != max_attempts:
            attempt += 1
            self._match(order, order_side, ob, target_price, max_attempts, attempt)

        return MatchResult(1, None)

    def _handle_new(self, payload: dict) -> None:
        """
        Handles the result of a new order by matching it against the order book.
        Depending on the order type (market or limit), the order is either matched immediately
        or added to the order book for future matching. If the order is filled, take profit and
        stop loss orders are placed if applicable.

        Args:
            payload (dict): The order data, including order type, side, price, and quantity.
        """
        ob = self._order_books[payload["instrument"]]
        order = Order(payload, Tag.ENTRY, payload["side"])

        func: dict[OrderType, Callable] = {
            OrderType.MARKET: self._handle_market_order,
            OrderType.LIMIT: self._handle_limit_order,
        }[payload["order_type"]]

        result: MatchResult = func(order, ob)

        if payload["order_type"] == OrderType.LIMIT:
            return
        print(result)
        if result.outcome == 2:
            ob.set_price(result.price)
            payload["status"] = OrderStatus.FILLED
            payload["standing_quantity"] = payload["quantity"]
            payload["filled_price"] = result.price
            # self._place_tp_sl(order, ob)
        else:
            ob.append(order, payload["price"])
            if payload["standing_quantity"] != payload["quantity"]:
                payload["status"] = OrderStatus.PARTIALLY_FILLED

        self.pusher.append(payload)

    def _handle_market_order(self, order: Order, ob: OrderBook) -> MatchResult:
        return self._match(order.payload, Side.BUY, ob, order.payload["price"])

    def _handle_limit_order(self, order: Order, ob: OrderBook) -> None:
        ob.append(order, order.payload["limit_price"])

    def _handle_touched_orders(
        self,
        orders: Iterable[Order],
        price: float,
        ob: OrderBook,
        filled_orders: list[tuple[Order, int]],
    ) -> None:
        return super()._handle_touched_orders(orders, price, ob, filled_orders)
