import asyncio
import json

from datetime import datetime
from collections.abc import Iterable
from random import random
from r_mutex import LockClient
from typing import Callable, TypedDict, Tuple

from config import SPOT_QUEUE_KEY, REDIS_CLIENT
from enums import OrderStatus, OrderType, Side
from .base_engine import BaseEngine
from ..enums import Tag
from ..exc import PositionNotFound
from ..order import Order
from ..orderbook.orderbook import OrderBook
from ..pusher import Pusher
from ..typing import EnginePayload, EnginePayloadCategory, MatchResult, MatchOutcome
from ..utils import (
    # EnginePayloadCategory,
    # EnginePayload,
    calc_buy_pnl,
    calculate_upl,
    # MatchResult,
)


class SpotCloseOrderPayload(TypedDict):
    quantity: int
    order_ids: Tuple[str]
    instrument: str
    price: float


# IN CONSTRUCTION
class SpotEngine(BaseEngine):
    def __init__(self, instrument_lock: LockClient, pusher: Pusher) -> None:
        super().__init__(instrument_lock, pusher)
        self.count = 0

    async def _listen(self) -> None:
        """Listens to the pubsub channel for incoming orders and delegates them to appropriate handlers."""
        await asyncio.sleep(0)

        handlers: dict[EnginePayloadCategory, Callable] = {
            EnginePayloadCategory.NEW: self.place_order,
            EnginePayloadCategory.MODIFY: self._handle_modify,
            EnginePayloadCategory.CLOSE: self.close_order,
            EnginePayloadCategory.CANCEL: self._handle_cancel,
        }

        async with REDIS_CLIENT.pubsub() as ps:
            await ps.subscribe(SPOT_QUEUE_KEY)
            async for message in ps.listen():
                if message["type"] == "subscribe":
                    continue

                payload: EnginePayload = json.loads(message["data"])
                func = handlers[payload["category"]]

                if asyncio.iscoroutine(func):
                    await func(json.loads(payload["content"]))
                else:
                    func(json.loads(payload["content"]))

    def _handle_touched_orders(
        self,
        orders: Iterable[Order],
        price: float,
        ob: OrderBook,
        filled_orders: list[tuple[Order, int]],
    ) -> None:
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
                order.payload["closed_price"] = price
                order.payload["unrealised_pnl"] = order.payload["standing_quantity"] = (
                    0.0
                )
                order.payload["realised_pnl"] += calc_buy_pnl(
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

    def _match(
        self,
        order: dict,
        order_side: Side,
        ob: OrderBook,
        price: float,
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
        book = "asks" if order_side == Side.BID else "bids"
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

        return MatchResult(1, None)

    async def place_order(self, payload: dict) -> None:
        """
        Handles the result of a new order by matching it against the order book.
        Depending on the order type (market or limit), the order is either
        matched immediately or added to the order book for future matching.
        If the order is filled, take profit and stop loss orders are placed
        if applicable.

        Args:
            payload (dict): The order data, including order type, side, price,
                and quantity.
        """

        ob = self._order_books[payload["instrument"]]
        order = Order(payload, Tag.ENTRY, Side.BID)

        func: dict[OrderType, Callable] = {
            OrderType.MARKET: self._handle_market_order,
            OrderType.LIMIT: self._handle_limit_order,
        }[payload["order_type"]]

        # Only here for testing
        self.count += 1
        if self.count % 2 == 0 and payload["order_type"] == OrderType.MARKET:
            result = MatchResult(2, round(random() * 100, 2))
        else:
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
        return self._match(order.payload, Side.BID, ob, order.payload["price"])

    def _handle_limit_order(self, order: Order, ob: OrderBook) -> None:
        ob.append(order, order.payload["limit_price"])

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
                    Side.ASK,
                ),
                order.payload["take_profit"],
            )

        if order.payload["stop_loss"] is not None:
            ob.append(
                Order(
                    order.payload,
                    Tag.STOP_LOSS,
                    Side.ASK,
                ),
                order.payload["stop_loss"],
            )

    def close_order(self, payload: SpotCloseOrderPayload) -> None:
        """
        Generates and attempts to match a sell order for each orderid
        passed within the payload. If a prtial fill occurs or the requested
        quantity is fulfilled, the loop is exited.

        Args:
            payload (CloseOrderPayload)
        """
        ob = self._order_books[payload["instrument"]]
        requested_quantity = payload["quantity"]
        execution_price: float = payload["price"]

        for oid in payload["order_ids"]:
            try:
                pos = ob.get(oid)
            except PositionNotFound:
                continue

            og_standing_quantity: float = pos.entry_order.payload["standing_quantity"]
            taken_standing_quantity: float = min(
                og_standing_quantity, requested_quantity
            )
            dummy_order = {
                **pos.entry_order.payload,
                "standing_quantity": taken_standing_quantity,
            }

            result: MatchResult = self._match(
                dummy_order, Side.ASK, ob, execution_price
            )

            cleared_quantity: int = (
                taken_standing_quantity - dummy_order["standing_quantity"]
            )

            if result.outcome == 2:
                pos.entry_order.payload["standing_quantity"] -= taken_standing_quantity
                execution_price = result.price

                if pos.entry_order.payload["standing_quantity"] == 0:
                    ob.remove_all(pos.entry_order)
                    pos.entry_order.payload["status"] = OrderStatus.CLOSED
                    pos.entry_order.payload["close_price"] = result.price
                    pos.entry_order.payload["closed_at"] = datetime.now()
                    pos.entry_order.payload["realised_pnl"] += calc_buy_pnl(
                        pos.entry_order.payload["filled_price"] * og_standing_quantity,
                        pos.entry_order.payload["filled_price"],
                        result.price,
                    )
                    pos.entry_order.payload["unrealised_pnl"] = 0

                self.pusher.append(pos.entry_order.payload, speed="fast")
                self.pusher.append(
                    {
                        "user_id": pos.entry_order.payload["user_id"],
                        "amount": pos.entry_order.payload["realised_pnl"],
                    },
                    "balance",
                )
            else:
                pos.entry_order.payload["standing_quantity"] -= cleared_quantity

                if result.outcome == 1:
                    pos.entry_order.payload["status"] = OrderStatus.PARTIALLY_CLOSED

                self.pusher.append(pos.entry_order.payload)
                break

            requested_quantity -= cleared_quantity

            if requested_quantity == 0:
                break
