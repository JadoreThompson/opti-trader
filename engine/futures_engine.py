import asyncio
import json

from datetime import datetime
from collections.abc import Iterable
from r_mutex import LockClient
from typing import Callable, TypedDict

from config import FUTURES_QUEUE_KEY, REDIS_CLIENT
from enums import OrderStatus, OrderType, Side
from .base_engine import BaseEngine
from .enums import Tag
from .order import Order
from .orderbook import OrderBook
from .position import Position
from .position_manager import PositionManager
from .pusher import Pusher
from .typing import (
    EnginePayload, 
    EnginePayloadCategory,
    MatchResult,
    MatchOutcome
)
from .utils import (    
    calc_sell_pl,
    calc_buy_pl,
    calculate_upl,
)


class FuturesCloseOrderPayload(TypedDict):
    order_id: str
    instrument: str
    price: float


class FuturesEngine(BaseEngine):
    def __init__(
        self,
        instrument_lock: LockClient,
        pusher: Pusher,
    ) -> None:
        super().__init__(instrument_lock, pusher)
        self._position_manager = PositionManager()

    async def _listen(self) -> None:
        """
        Listens to the pubsub channel for incoming orders and
        delegates them to appropriate handlers.
        """
        await asyncio.sleep(0)

        handlers: dict[EnginePayloadCategory, Callable] = {
            EnginePayloadCategory.NEW: self.place_order,
            EnginePayloadCategory.MODIFY: self._handle_modify,
            EnginePayloadCategory.CLOSE: self._handle_close,
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
                payload = message['data']
                handlers[payload["category"]](payload["content"])

    def place_order(self, payload: dict) -> None:
        """
        Handles the result of a new order by matching it against the order book.
        Depending on the order type (market or limit), the order is either matched
        immediately or added to the order book for future matching.

        If the order is filled, take profit and stop loss orders are placed if applicable.

        Args:
            payload (dict): The order data, including order type, side, price, and quantity.
        """
        ob = self._order_books.setdefault(payload["instrument"], OrderBook())
        order = Order(payload, Tag.ENTRY, payload["side"])

        if payload["order_type"] == OrderType.LIMIT:
            return ob.append(order, payload["limit_price"])

        result: MatchResult = self._match(order, ob)

        if result.outcome == MatchOutcome.SUCCESS:
            ob.set_price(result.price)
            
            payload["status"] = OrderStatus.FILLED
            payload["standing_quantity"] = payload["quantity"]
            payload["filled_price"] = result.price            
            
            self._position_manager.create(order)
            self._place_tp_sl(order, ob)
        else:
            ob.append(order, result.price)
            if payload["standing_quantity"] != payload["quantity"]:
                payload["status"] = OrderStatus.PARTIALLY_FILLED

        self.pusher.append(payload)

    def _match(self, order: Order, ob: OrderBook) -> MatchResult:
        """
        Matches order against opposing book

        Args:
            order (dict)
            order_side (Side)
            ob (Orderbook): orderbook
            price (float): price to target

        Returns:
            MatchResult:
                Filled: (2, price)
                Partially filled: (1, None)
                Not filled: (0, None)
        """
        book_to_match = "asks" if order.side == Side.BID else "bids"
        aggresive_payload = order.payload

        target_price = ob.best_ask if order.side == Side.BID else ob.best_bid
        if target_price is None:
            return MatchResult(MatchOutcome.FAILURE, None)

        touched_orders: list[Order] = []
        filled_orders: list[tuple[Order, int]] = []

        for resting_order in ob.get_orders(target_price, book_to_match):
            if aggresive_payload["standing_quantity"] == 0:
                break

            og_resting_qty = resting_order.payload["standing_quantity"]
            match_qty = min(og_resting_qty, aggresive_payload["standing_quantity"])

            resting_order.payload["standing_quantity"] -= match_qty
            aggresive_payload["standing_quantity"] -= match_qty

            if resting_order.payload["standing_quantity"] == 0:
                filled_orders.append((resting_order, og_resting_qty))
            else:
                touched_orders.append((resting_order, og_resting_qty))

        self._handle_touched_orders(touched_orders, filled_orders, target_price, ob)
        self._handle_filled_orders(filled_orders, target_price, ob)

        if aggresive_payload["standing_quantity"] == 0:
            return MatchResult(MatchOutcome.SUCCESS, target_price)
        return MatchResult(MatchOutcome.PARTIAL, target_price)

    def _place_tp_sl(
        self, order: Order, ob: OrderBook, pos: Position | None = None
    ) -> None:
        """
        Handles the submission of an orders take profit and stop loss
        to the orderbook. Must only be called for orders that are filled

        Args:
            order (Order)
            ob (OrderBook)
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
            pos.take_profit = Order(
                order.payload,
                Tag.TAKE_PROFIT,
                Side.ASK if order.side == Side.BID else Side.BID,
            )
            ob.append(pos.take_profit, order.payload["take_profit"])

        if order.payload["stop_loss"] is not None:
            pos.stop_loss = Order(
                order.payload,
                Tag.STOP_LOSS,
                Side.ASK if order.side == Side.BID else Side.BID,
            )
            ob.append(pos.stop_loss, order.payload["stop_loss"])

    def _handle_filled_orders(
        self, orders: Iterable[tuple[Order, int]], price: float, ob: OrderBook
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
            ob.remove(order, price)

            if order.tag == Tag.ENTRY:
                order.payload["status"] = OrderStatus.FILLED
                order.payload["standing_quantity"] = order.payload["quantity"]
                order.payload["filled_price"] = price
                self._position_manager.create(order)
                self._place_tp_sl(order, ob)
                calculate_upl(order, price, ob)
            else:
                pos = self._position_manager.get(order.payload['order_id'])
                if pos.take_profit and pos.take_profit != order:
                    ob.remove(pos.take_profit, order.payload['take_profit'])
                if pos.stop_loss and pos.stop_loss != order:
                    ob.remove(pos.stop_loss, order.payload['stop_loss'])
                    
                self._position_manager.remove(order.payload["order_id"])
                order.payload["status"] = OrderStatus.CLOSED
                order.payload["closed_at"] = datetime.now()
                order.payload["unrealised_pnl"] = 0.0
                order.payload["standing_quantity"] = 0
                order.payload["closed_price"] = price

                if order.payload["side"] == Side.BID:
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
        ob: OrderBook,
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
        for order, standing_qty in orders:
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
                filled_orders.append((order, standing_qty))
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

    def _handle_close(self, payload: FuturesCloseOrderPayload) -> None:
        """
        DO NOT CALL!!!
        Handles the result from attempting to match the order
        in order to close it

        Args:
            payload (dict)
        """
        ob = self._order_books[payload["instrument"]]
        pos = ob.get(payload["order_id"])

        if pos is None:
            return

        ob.remove_all(pos.order)
        before_standing_quantity: int = pos.order.payload["standing_quantity"]
        result: MatchResult = self._match(
            pos.order.payload,
            Side.ASK if pos.order.side == Side.BID else Side.ASK,
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
            calc_pl_fn = calc_buy_pl if pos.order.side == Side.BID else calc_sell_pl
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

    
    def _handle_append_ob(self, data: dict) -> None:
        self._order_books.setdefault(data['instrument'], OrderBook(data['price']))