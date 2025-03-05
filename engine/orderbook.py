import asyncio
import random
import warnings

from collections import deque
from typing import Literal, Optional
from uuid import UUID
from sqlalchemy import update

from config import REDIS_CLIENT
from db_models import Users
from enums import OrderStatus, Side
from utils.db import get_db_session
from .enums import Tag
from .order import Order
from .position import Position
from .pusher import Pusher
from .utils import calculate_upl


class OrderBook:
    def __init__(
        self,
        lock,
        instrument: str,
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

    def append(self, order: Order, price: float, **kwargs) -> None:
        """
        Appends order to tracking and to the book
        """
        create_position = False

        try:
            pos: Position = self.get(order.payload["order_id"])

            if order.tag == Tag.TAKE_PROFIT:
                pos.take_profit = order
            else:
                pos.stop_loss = order
        except ValueError:
            create_position = True

        if create_position:
            self._tracker.setdefault(order.payload["order_id"], Position(order))

        if order.side == Side.BUY:
            self.bids.setdefault(price, [])
            self.bids[price].append(order)

        elif order.side == Side.SELL:
            self.asks.setdefault(price, [])
            self.asks[price].append(order)

    def track(self, order: Order) -> Position:
        pos = self._tracker.setdefault(order.payload["order_id"], Position(order))

        if order.tag == Tag.STOP_LOSS:
            pos.stop_loss = order
        elif order.tag == Tag.TAKE_PROFIT:
            pos.take_profit = order

        return pos

    def remove(self, order: Order, mode: Literal["single", "all"] = "single") -> None:
        func = {"single": self.remove_single, "all": self.remove_all}.get(mode)

        if func:
            func(order)
        else:
            raise ValueError("Mode must be of all, single")

    def remove_single(self, order: Order) -> None:
        if order.tag == Tag.ENTRY:
            price = order.payload["price"] or order.payload["limit_price"]
        elif order.tag == Tag.TAKE_PROFIT:
            price = order.payload["take_profit"]
        elif order.tag == Tag.STOP_LOSS:
            price = order.payload["stop_loss"]

        if order.side == Side.BUY:
            try:
                self.bids[price].remove(order)
                if not self.bids[price]:
                    self.bids.pop(price, None)
            except (ValueError, KeyError):
                pass

        elif order.side == Side.SELL:
            try:
                self.asks[price].remove(order)
                if not self.asks[price]:
                    self.asks.pop(price, None)
            except (ValueError, KeyError):
                pass

    def remove_all(self, order: Order) -> None:
        pos: Position = self._tracker.pop(order.payload["order_id"])
        self.remove_single(order)

        if pos.take_profit is not None:
            self.remove_single(pos.take_profit)
        if pos.stop_loss is not None:
            self.remove_single(pos.stop_loss)

    def get(self, order_id: str | UUID, **kwargs) -> Optional[Position]:
        pos = self._tracker.get(order_id)
        if pos is None:
            raise ValueError("Position related to order doesn't exist")
        return pos

    def best_price(self, side: Side, price: float) -> Optional[float]:
        price_levels = self.bid_levels if side == Side.BUY else self.ask_levels
        price_levels = list(price_levels)

        if not price_levels:
            return

        if any(price == None for price in price_levels):
            return

        if side == Side.SELL:
            cleaned_prices = {
                key: abs(price - key)
                for key in price_levels
                if key >= price and len(self.asks[key]) > 0
            }
        else:
            cleaned_prices = {
                key: abs(price - key)
                for key in price_levels
                if key <= price and len(self.bids[key]) > 0
            }

        if cleaned_prices:
            return sorted(cleaned_prices.items(), key=lambda item: item[1])[0][0]

    def set_price(self, price: float) -> None:
        self._price = price
        self._price_queue.append(price)

    async def _publish_price(
        self,
    ) -> None:
        await REDIS_CLIENT.set(f"{self.instrument}.price", self._price)
        await REDIS_CLIENT.publish(f"{self.instrument}.live", self._price)

        randnum = lambda: round(random.random() * 100, 2)

        while True:
            # self._price_queue.extend([randnum() for _ in range(5)])
            self._price = randnum()
            self._price_queue.append(self._price)
            
            try:
                price = self._price_queue.popleft()
            except IndexError as e:
                price = self._price = randnum()
                

            try:
                await self._update_upl(price)
                await REDIS_CLIENT.set(f"{self.instrument}.price", price)
                await REDIS_CLIENT.publish(f"{self.instrument}.live", price)
            except Exception as e:
                if not isinstance(e, IndexError):
                    print("[orderbook][_publish_price] - ", type(e), str(e))

            await asyncio.sleep(self._price_delay)

    async def _update_upl(self, price: float) -> None:
        if self._tracker:
            tracker_copy = self._tracker.copy()
            for _, pos in tracker_copy.items():
                if pos.order.payload["status"] in (
                    OrderStatus.FILLED,
                    OrderStatus.PARTIALLY_CLOSED,
                ):
                    calculate_upl(pos.order, price, self)
                    self.pusher.append(pos.order.payload, mode="fast")

                    if pos.order.payload["status"] == OrderStatus.CLOSED:
                        # print('Appending to the price queue')
                        self.pusher.append(
                            {
                                "user_id": pos.order.payload["user_id"],
                                "amount": pos.order.payload["realised_pnl"],
                            },
                            "balance",
                        )

            # async with get_db_session() as sess:
            #     await sess.execute(
            #         update(Users),
            #         [pos.order.payload for _, pos in tracker_copy.items()],
            #     )
            #     await sess.commit()

    @property
    def price(self) -> float:
        return self._price

    def __getitem__(self, book: Literal["bids", "asks"]) -> dict:
        return self.bids if book == "bids" else self.asks

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"Orderbook({self.instrument}, price={self.price}, bids={sum(len(self.bids[key]) for key in self.bids)}, asks={sum(len(self.asks[key]) for key in self.asks)})"
