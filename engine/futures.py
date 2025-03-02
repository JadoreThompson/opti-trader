import asyncio
import multiprocessing
import queue
import threading
import time

from collections import namedtuple
from collections.abc import Iterable
from uuid import uuid4
from sqlalchemy import update

from db_models import Orders
from enums import OrderStatus, OrderType, Side
from utils.db import get_db_session
from .enums import Tag
from .order import Order
from .orderbook import Orderbook


MatchResult = namedtuple(
    "MatchResult",
    (
        "outcome",
        "price",
    ),
)

class FuturesEngine:
    def __init__(self, queue: multiprocessing.Queue = None) -> None:
        self.last_price = None
        self.thread: threading.Thread = None
        self.loop: asyncio.AbstractEventLoop = None
        
        self._init_loop()
        self.loop.create_task(self._publish_changes())
        
        self.queue = queue or multiprocessing.Queue()
        self._order_books: dict[str, Orderbook] = {
            "BTCUSD": Orderbook(self.loop, "BTCUSD", 37),
        }
        self._collection: list[dict] = []

    def _init_loop(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._set_loop, daemon=True)
        self.thread.start()
        
        if not self.loop.is_running():
            raise RuntimeError("Loop is dead")

    def _set_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self) -> None:
        while True:
            try:
                message = self.queue.get()
                self._handle(message)
            except queue.Empty:
                continue

    def _handle(self, order_data: dict):
        ob = self._order_books[order_data["instrument"]]
        order = Order(order_data, Tag.ENTRY, order_data["side"])
        
        func: dict[OrderType, callable] = {
            OrderType.MARKET: self._handle_market,
            OrderType.LIMIT: self._handle_limit,
        }[order_data["order_type"]]

        result: MatchResult = func(order, ob)

        if order_data["order_type"] == OrderType.LIMIT:
            return
        # print(result)
        if result.outcome == 2:
            ob.set_price(result.price)
            order_data["status"] = OrderStatus.FILLED
            order_data["standing_quantity"] = order_data["quantity"]
            self._place_tp_sl(order, ob)
        else:
            ob.append(order, order_data["price"])
            if order_data["standing_quantity"] != order_data["quantity"]:
                order_data["status"] = OrderStatus.PARTIALLY_FILLED
            # print(
            #     f"[futures][_match] Original SQ - {ogsq}, New SQ - {order_data['standing_quantity']}"
            # )
        self._collection.append(order_data)

    def _handle_market(self, order: Order, ob: Orderbook):
        order.order["price"] = ob.price
        return self._match(order.order, ob, order.order["price"], 20)

    def _handle_limit(self, order: Order, ob: Orderbook) -> None:
        ob.append(order, order.order["limit_price"])

    def _match(
        self,
        order: dict,
        ob: Orderbook,
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
        filled: list[Order] = []
        book = "bids" if order["side"] == Side.SELL else "asks"
        target_price = ob.best_price(order["side"], price)
        # print(f"[futures][_match] - Attempt: {attempt} Price: {f"${price}" if price else price} - ID: {order['order_id']}")

        if target_price is None:
            return MatchResult(0, None)

        if target_price not in ob[book]:
            return MatchResult(0, None)

        # if self.last_price != target_price:
        #     self.last_price = target_price
        #     print("Target Price: ", self.last_price)

        for existing_order in ob[book][target_price]:
            leftover_quant = (
                existing_order.order["standing_quantity"] - order["standing_quantity"]
            )

            if leftover_quant >= 0:
                touched.append(existing_order)
                existing_order.order["standing_quantity"] -= order["standing_quantity"]
                order["standing_quantity"] = 0
            else:
                filled.append(existing_order)
                order["standing_quantity"] -= existing_order.order["standing_quantity"]
                existing_order.order["standing_quantity"] = 0

            if order["standing_quantity"] == 0:
                break

        self._handle_filled_orders(filled, ob, tag=uuid4())

        for t_order in touched:
            if t_order.tag == Tag.ENTRY:
                t_order.order["status"] = OrderStatus.PARTIALLY_FILLED
            else:
                t_order.order["status"] = OrderStatus.PARTIALLY_CLOSED

            self._collection.append(t_order.order)

        if order["standing_quantity"] == 0:
            return MatchResult(2, target_price)

        # if order["standing_quantity"] > 0:
        if attempt != max_attempts:
            attempt += 1
            self._match(order, ob, target_price, max_attempts, attempt)

        return MatchResult(1, None)

    def _place_tp_sl(self, order: Order, ob: Orderbook):
        ob.track(order)

        if order.order["take_profit"] is not None:
            tp_order = Order(
                order.order,
                Tag.TAKE_PROFIT,
                Side.SELL if order.order["side"] == Side.BUY else Side.BUY,
            )
            ob.append(tp_order, order.order["take_profit"], tag=uuid4())

        if order.order["stop_loss"] is not None:
            sl_order = Order(
                order.order,
                Tag.STOP_LOSS,
                Side.SELL if order.order["side"] == Side.BUY else Side.BUY,
            )
            ob.append(sl_order, order.order["stop_loss"], tag=uuid4())

    def _handle_filled_orders(
        self, orders: Iterable[Order], ob: Orderbook, **kwargs
    ) -> None:
        for order in orders:
            ob.remove(order)
            # print(f"[futures][_handle_filled_orders] Tag: ", order.tag)
            if order.tag == Tag.ENTRY:    
                # print(order.order['order_id'], order.order['status'])
                order.order["status"] = OrderStatus.FILLED
                self._place_tp_sl(order, ob)
            else:
                # print(f"[futures][_handle_filled_orders] - {str(order.order['order_id']):*^20} is a {order.tag} order")
                ob.remove(order, 'all')
                order.order["status"] = OrderStatus.CLOSED
            self._collection.append(order.order)
        # print(f"[futures][handle_filled_orders] Appended: {orders}")

    async def _publish_changes(self) -> None:
        while True:
            if self._collection:
                # print("[futures][publish_changes]", self._collection[:3])
                try:
                    async with get_db_session() as sess:
                        await sess.execute(update(Orders), self._collection)
                        await sess.commit()
                    self._collection.clear()
                except Exception as e:
                    print(
                        f"[futures][publish_changes] => Error: type - ",
                        type(e),
                        "content - ",
                        str(e),
                    )
            await asyncio.sleep(1.5)
