import asyncio
import multiprocessing
import queue
import threading
import time
import warnings

from collections import namedtuple
from collections.abc import Iterable
from uuid import uuid4

from engine.pusher import Pusher
from enums import OrderStatus, OrderType, Side
from .enums import Tag
from .order import Order
from .orderbook import OrderBook
from .utils import calc_sell_pl, calc_buy_pl, calculate_upl


MatchResult = namedtuple(
    "MatchResult",
    (
        "outcome",
        "price",
    ),
)


class FuturesEngine:
    def __init__(
        self, queue: multiprocessing.Queue = None, pusher: Pusher = None
    ) -> None:
        self.pusher = pusher or Pusher()
        self.last_price = None
        self.thread: threading.Thread = None
        self.loop: asyncio.AbstractEventLoop = None

        self._init_loop()
        self.loop.create_task(self.pusher.run())
        
        i = 1
        while i < 5:
            time.sleep(i)
            if self.pusher.is_running:
                break
            warnings.warn(f"Pusher not running - sleeping {i} seconds")
            i += 1

        self.queue = queue or multiprocessing.Queue()
        self._order_books: dict[str, OrderBook] = {
            "BTCUSD": OrderBook(self.loop, "BTCUSD", 37, self.pusher),
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
        order.payload["price"] = ob.price
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
        filled: list[Order] = []
        book = "bids" if order["side"] == Side.SELL else "asks"
        target_price = ob.best_price(order["side"], price)

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
                filled.append(existing_order)
                order["standing_quantity"] -= existing_order.payload[
                    "standing_quantity"
                ]
                existing_order.payload["standing_quantity"] = 0

            if order["standing_quantity"] == 0:
                break

        if touched or filled:
            ob.set_price(price)

        for t_order in touched:
            if t_order.tag == Tag.ENTRY:
                if t_order.payload["standing_quantity"] > 0:
                    t_order.payload["status"] = OrderStatus.PARTIALLY_FILLED
                else:
                    filled.append(t_order)
            else:
                t_order.payload["status"] = OrderStatus.PARTIALLY_CLOSED

            calculate_upl(t_order, target_price, ob)
            self.pusher.append(t_order.payload)

        self._handle_filled_orders(filled, ob, target_price, tag=uuid4())

        if order["standing_quantity"] == 0:
            return MatchResult(2, target_price)

        if attempt != max_attempts:
            attempt += 1
            self._match(order, ob, target_price, max_attempts, attempt)

        return MatchResult(1, None)

    def _place_tp_sl(self, order: Order, ob: OrderBook):
        ob.track(order)

        if order.payload["take_profit"] is not None:
            tp_order = Order(
                order.payload,
                Tag.TAKE_PROFIT,
                Side.SELL if order.payload["side"] == Side.BUY else Side.BUY,
            )
            ob.append(tp_order, order.payload["take_profit"], tag=uuid4())

        if order.payload["stop_loss"] is not None:
            sl_order = Order(
                order.payload,
                Tag.STOP_LOSS,
                Side.SELL if order.payload["side"] == Side.BUY else Side.BUY,
            )
            ob.append(sl_order, order.payload["stop_loss"], tag=uuid4())

    def _handle_filled_orders(
        self, orders: Iterable[Order], ob: OrderBook, price: float, **kwargs
    ) -> None:
        for order in orders:
            ob.remove(order)

            if order.tag == Tag.ENTRY:
                order.payload["status"] = OrderStatus.FILLED
                order.payload["standing_quantity"] = order.payload["quantity"]
                order.payload["filled_price"] = price
                self._place_tp_sl(order, ob)
            else:
                ob.remove(order, "all")
                order.payload["status"] = OrderStatus.CLOSED
                order.payload["closed_price"] = price
                order.payload["unrealised_pnl"] = 0

                if order.payload["side"] == Side.BUY:
                    order.payload["realised_pnl"] = calc_buy_pl(
                        order.payload["amount"], order.payload["filled_price"], price
                    )
                else:
                    order.payload["realised_pnl"] = calc_sell_pl(
                        order.payload["amount"], order.payload["filled_price"], price
                    )

            if order.payload["status"] == OrderStatus.FILLED:
                calculate_upl(order, price, ob)

            self.pusher.append(order.payload)

    def _calculate_upl(self, order: Order, price: float, ob: OrderBook) -> None:
        upl: float = None

        if order.payload["filled_price"] is None:
            return

        if order.payload["side"] == Side.SELL:  # Must be a buy
            upl = calc_buy_pl(
                order.payload["amount"], order.payload["filled_price"], price
            )
        else:
            upl = calc_sell_pl(
                order.payload["amount"],
                order.payload["filled_price"],
                price,
            )
        if order.payload["unrealised_pnl"] is not None:
            if upl <= order.payload["amount"] * -1:
                ob.remove(order, "all")
                order.payload["status"] = OrderStatus.CLOSED
                order.payload["closed_price"] = price
                order.payload["unrealised_pnl"] = 0

                order.payload["realised_pnl"] = upl
                return
        
        order.payload["unrealised_pnl"] = upl
