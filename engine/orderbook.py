import asyncio

from collections import deque
from typing import Literal, Optional

from config import REDIS_CLIENT
from enums import Side
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
        self.bids: dict[float, list[Position]] = {}
        self.asks: dict[float, list[Position]] = {}
        self.bid_levels = self.bids.keys()
        self.ask_levels = self.asks.keys()
        
    def append(self, order: dict, price: float) -> None:
        if order['side'] == 'buy':
            self.bids.setdefault(price, [])
            self.bids[price].append(Position(order))
            
        elif order['side'] == 'sell':
            self.asks.setdefault(price, [])
            self.asks[price].append(Position(order))
            
    def remove(self, position: Position):
        price = position.order['price'] or position.order['limit_price']
        
        if position.order['side'] == Side.BUY:
            try:
                self.bids[price].remove(position)
                if not self.bids[price]:
                    self.bids.pop(price, None)
            except (ValueError, KeyError):
                pass
            
        elif position.order['side'] == Side.SELL:
            try:
                self.asks[price].remove(position)
                if not self.asks[price]:
                    self.asks.pop(price, None)
            except (ValueError, KeyError) as e:
                pass
            
    def best_price(self, side: Side, price: float) -> Optional[float]:
        price_levels = self.bid_levels if side == Side.BUY else self.ask_levels
        price_levels = list(price_levels)
        
        if not price_levels:
            return

        if price_levels[0] == None:
            return
        
        if side == Side.SELL:
            cleaned_prices = {
                key: abs(price - key)
                for key in price_levels
                if key >= price
                and len(self.asks[key]) > 0
            }
        else:
            cleaned_prices = {
                key: abs(price - key)
                for key in price_levels
                if key <= price
                and len(self.bids[key]) > 0
            }
            
        if cleaned_prices:
            return sorted(cleaned_prices.items(), key=lambda item: item[1])[0][0]
        
    def set_price(self, price: float) -> None:
        self._price_queue.append(price)
        
    async def _publish_price(self,) -> None:
        await REDIS_CLIENT.set(f"{self.instrument}.price", str(self._price))
        while True:
            try:
                self._price = self._price_queue.popleft()
                await REDIS_CLIENT.set(f"{self.instrument}.price", str(self._price))
            except IndexError:
                pass
            
            await asyncio.sleep(1)
        
    @property
    def price(self) -> float:
        return self._price
        
    def __getitem__(self, book: Literal['bids', 'asks']) -> dict:
        return self.bids if book == 'bids' else self.asks
        
    def __repr__(self) -> str:
        return f'Orderbook({self.instrument}, price={self.price}, bids={sum(len(self.bids[key]) for key in self.bids)}, asks={sum(len(self.asks[key]) for key in self.asks)})'
    