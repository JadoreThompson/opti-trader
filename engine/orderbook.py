import asyncio
import json
import random

from collections import deque
from typing import Literal, Optional
from uuid import UUID

from config import REDIS_CLIENT
from enums import Side
from .enums import Tag
from .order import Order
from .position import Position


class Orderbook:
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        instrument: str,
        price: float = 150,
    ) -> None:
        self._price = price
        self._price_queue = deque()
        self._loop = loop
        self._loop.create_task(self._publish_price())

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
        create_position = True

        if order.order["order_id"] in self._tracker:
            create_position = False
            pos: Position = self._tracker[order.order["order_id"]]

            if order.tag == Tag.TAKE_PROFIT:
                pos.take_profit = order
            else:
                pos.stop_loss = order

        if create_position:
            self._tracker.setdefault(order.order['order_id'], Position(order))

        if order.side == Side.BUY:
            self.bids.setdefault(price, [])
            self.bids[price].append(order)

        elif order.side == Side.SELL:
            self.asks.setdefault(price, [])
            self.asks[price].append(order)

    def track(self, order: Order) -> Position:
        pos = self._tracker.setdefault(order.order["order_id"], Position(order))

        if order.tag == Tag.STOP_LOSS:
            pos.stop_loss = order
        elif order.tag == Tag.TAKE_PROFIT:
            pos.take_profit = order

        return pos

    def remove(self, order: Order, mode: Literal["single", "all"] = "single") -> None:
        remove_func = {
            "single": self.remove_single,
            "all": self.remove_all
        }.get(mode)

        if remove_func:
            remove_func(order)
        else:
            raise ValueError(f"Mode must be of all, single")

    def remove_single(self, order: Order) -> None:
        price = order.order["price"] or order.order["limit_price"]

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
        pos: Position = self.get(order.order['order_id'])
        self.remove_single(pos.order)
        
        if pos.take_profit is not None:
            self.remove_single(pos.take_profit)
        if pos.stop_loss is not None:
            self.remove_single(pos.stop_loss)
        
        del self._tracker[order.order['order_id']]

    def get(self, order_id: str) -> Optional[Position]:
        if order_id not in self._tracker:
            raise ValueError("Position related to order doesn't exist")
        return self._tracker[order_id]

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
        await REDIS_CLIENT.set(f"{self.instrument}.price", str(self._price))
        randnum = lambda: round(random.random() * 100, 2)

        while True:
            # self._price = randnum()
            # self._price_queue.append(self._price)
            # print(self._price_queue)

            self._price = randnum()
            self._price_queue.append(self._price)
            try:
                await REDIS_CLIENT.set(
                    f"{self.instrument}.price", str(self._price_queue.popleft())
                )
            except Exception as e:
                if not isinstance(e, IndexError):
                    print(f"Redis error: {e}")

            await asyncio.sleep(1)

    @property
    def price(self) -> float:
        return self._price

    def __getitem__(self, book: Literal["bids", "asks"]) -> dict:
        return self.bids if book == "bids" else self.asks

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"Orderbook({self.instrument}, price={self.price}, bids={sum(len(self.bids[key]) for key in self.bids)}, asks={sum(len(self.asks[key]) for key in self.asks)})"
