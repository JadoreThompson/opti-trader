import asyncio
import random
import warnings

from collections import deque
from datetime import datetime
from r_mutex import Lock
from sqlalchemy import insert
from typing import Literal, Optional

from config import REDIS_CLIENT
from db_models import MarketData
from enums import OrderStatus, Side
from utils.db import get_db_session
from .enums import Tag
from .exceptions import PositionNotFound
from .order import Order
from .position import Position
from .pusher import Pusher
from .utils import calculate_upl


class OrderBook:
    """
    Manages the order book for a given trading instrument, handling bid and ask orders,
    price updates, and order tracking.

    The OrderBook maintains separate dictionaries for bids and asks, allowing efficient
    order management. It also tracks positions and updates unrealized profit/loss (UPL)
    based on price changes.

    Attributes:
        instrument (str): The trading instrument (e.g., "BTCUSD").
        lock (r_mutex.Lock): A threading lock to ensure safe access to shared resources.
        _price (float): The current market price of the instrument.
        _price_delay (float): The delay (in seconds) between price updates.
        _price_queue (deque): A queue storing price updates. Used to enable throttling of
            price upates
        pusher (Pusher): Used for consolidating updates to records of orders in DB
        bids (dict[float, list[Order]]): Stores bid orders, grouped by price level.
        asks (dict[float, list[Order]]): Stores ask orders, grouped by price level.
        bid_levels (dict_keys): A view of the bid price levels.
        ask_levels (dict_keys): A view of the ask price levels.
        _tracker (dict[str, Position]): Tracks positions associated with order IDs.
    """

    def __init__(
        self,
        instrument: str,
        lock: Lock,
        price: float = 150,
        pusher: Pusher = None,
        delay: float = 1,
    ) -> None:
        """Delay in seconds"""
        self.lock = lock
        self._price_delay = delay
        self._price = price
        self._price_queue = deque()

        if pusher is None:
            warnings.warn("Pusher not provided, configuring pusher")
            pusher = Pusher()
            asyncio.create_task(pusher.run())

        asyncio.create_task(self._publish_price())

        self.pusher = pusher
        self.instrument = instrument
        self.bids: dict[float, list[Order]] = {}
        self.asks: dict[float, list[Order]] = {}
        self.bid_levels = self.bids.keys()
        self.ask_levels = self.asks.keys()
        self._tracker: dict[str, Position] = {}

    def append(self, order: Order, price: float) -> Position:
        """
        Appends order to tracking and to the book

        Args:
            order (Order)
            price (float) - Price level to be appended to
        """
        create_position = False

        try:
            pos: Position = self.get(order.payload["order_id"])

            if order.tag == Tag.TAKE_PROFIT:
                pos.take_profit = order
            else:
                pos.stop_loss = order
        except PositionNotFound:
            create_position = True

        if create_position:
            pos = self._tracker.setdefault(order.payload["order_id"], Position(order))

        if order.side == Side.BUY:
            self.bids.setdefault(price, [])
            self.bids[price].append(order)

        elif order.side == Side.SELL:
            self.asks.setdefault(price, [])
            self.asks[price].append(order)

        return pos

    def track(self, order: Order) -> Position:
        """
        Appends an order to the tracker. If this is a take profit or stop loss
        order, it's appended to the position. 

        Args:
            order (Order)

        Returns:
            Position
        """
        pos = self._tracker.setdefault(order.payload["order_id"], Position(order))

        if order.tag == Tag.STOP_LOSS:
            pos.stop_loss = order
        elif order.tag == Tag.TAKE_PROFIT:
            pos.take_profit = order

        return pos

    def remove(self, order: Order) -> None:
        """
        Removes an order from the price level it situates. To be used
        when an order isn't in the filled state since it won't be situated
        within a price level. However it's stop loss and take profit order object
        can utilise this since they'll be situated in a price level.

        Args:
            order (Order)
        """
        if order.tag == Tag.ENTRY:
            price = order.payload["limit_price"] or order.payload["price"]
        elif order.tag == Tag.TAKE_PROFIT:
            price = order.payload["take_profit"]
        elif order.tag == Tag.STOP_LOSS:
            price = order.payload["stop_loss"]

        if order.side == Side.BUY:
            if order in self.bids.get(price, []):
                self.bids[price].remove(order)
            if price in self.bids:
                self.bids.pop(price, None)

        elif order.side == Side.SELL:
            if order in self.asks.get(price, []):
                self.asks[price].remove(order)
            if price in self.asks:
                self.asks.pop(price, None)

    def remove_all(self, order: Order) -> Position:
        """
        Removes the order and it's counterparts both from the
        tracker and their corresponding price levels

        Args:
            order (Order)

        Returns:
            Position
        """
        pos: Position = self._tracker.pop(order.payload["order_id"])
        self.remove(order)

        if pos.take_profit is not None:
            self.remove(pos.take_profit)
        if pos.stop_loss is not None:
            self.remove(pos.stop_loss)
        return pos
        

    def get(self, order_id: str) -> Position:
        """
        Retrieves the position object belonging to the order_id

        Args:
            order_id (str)

        Raises:
            PositionNotFound: Position with order id doesn't exist
        """
        pos = self._tracker.get(order_id)
        if pos is None:
            raise PositionNotFound("Position related to order doesn't exist")
        return pos

    def best_price(
        self, book: Literal["bids", "asks"], price: float
    ) -> Optional[float]:
        """
        Returns the closest price to the target(price passed in param) in the
        bid book if side is passed as Side.BUY or ask if Side.SELL with at least
        one order located within the price level.

        Args:
            book ("bids" or "asks"): The book you want to
        """
        price_levels = self.bid_levels if book == "bids" else self.ask_levels
        price_levels = list(price_levels)

        if not price_levels:
            return

        if any(price == None for price in price_levels):
            return

        if book == Side.SELL:
            cleaned_prices = {
                key: abs(price - key)
                for key in price_levels
                if key >= price and len(self.asks.get(key, [])) > 0
            }
        else:
            cleaned_prices = {
                key: abs(price - key)
                for key in price_levels
                if key <= price and len(self.bids.get(key, [])) > 0
            }

        if cleaned_prices:
            return sorted(cleaned_prices.items(), key=lambda item: item[1])[0][0]

    def set_price(self, price: float) -> None:
        """
        Sets price attribute to price in param along with appending to the queue
        Args:
            price (float)
        """
        self._price = price
        self._price_queue.append(price)

    async def _publish_price(
        self,
    ) -> None:
        """
        Periodically posts price to the pubsub channel and writes to the db
        """
        await REDIS_CLIENT.set(f"{self.instrument}.price", self._price)
        await REDIS_CLIENT.publish(f"{self.instrument}.live", self._price)

        randnum = lambda: round(random.random() * 100, 2)  # Here during dev

        while True:
            self._price = randnum()  # Here during dev
            self._price_queue.append(self._price)  # Here during dev

            try:
                price = self._price_queue.popleft()
            except IndexError:
                price = self._price = randnum()

            await REDIS_CLIENT.set(f"{self.instrument}.price", price)
            await REDIS_CLIENT.publish(f"{self.instrument}.live", price)

            async with self.lock:
                async with get_db_session() as sess:
                    await sess.execute(
                        insert(MarketData).values(
                            instrument=self.instrument,
                            time=datetime.now().timestamp(),
                            price=price,
                        )
                    )
                    await sess.commit()
            asyncio.create_task(self._update_upl(price))

            await asyncio.sleep(self._price_delay)

    async def _update_upl(self, price: float) -> None:
        """
        Updates upl for all filled and partially filled orders
        within the tracker
        
        Args:
            price (float)
        """
        if self._tracker:
            tracker_copy = self._tracker.copy()
            for _, pos in tracker_copy.items():
                if pos.order.payload["status"] in (
                    OrderStatus.FILLED,
                    OrderStatus.PARTIALLY_CLOSED,
                ):
                    calculate_upl(pos.order, price, self)
                    self.pusher.append(pos.order.payload, speed="fast")

                    if pos.order.payload["status"] == OrderStatus.CLOSED:
                        self.pusher.append(
                            {
                                "user_id": pos.order.payload["user_id"],
                                "amount": pos.order.payload["realised_pnl"],
                            },
                            "balance",
                        )

    @property
    def price(self) -> float:
        return self._price

    def __getitem__(self, book: Literal["bids", "asks"]) -> dict:
        return self.bids if book == "bids" else self.asks

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"Orderbook({self.instrument}, price={self.price}, bids={sum(len(self.bids[key]) for key in self.bids)}, asks={sum(len(self.asks[key]) for key in self.asks)})"
