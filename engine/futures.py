import asyncio
from collections import namedtuple
from collections.abc import Iterable
import multiprocessing
import queue
import threading
import time

from sqlalchemy import update

from db_models import Orders
from enums import OrderStatus, OrderType, Side
from utils.db import get_db_session

from .orderbook import Orderbook
from .position import Position


MatchResult = namedtuple('MatchResult', ('outcome', 'price',))


class FuturesEngine:
    def __init__(self, queue: multiprocessing.Queue = None) -> None:
        self.thread: threading.Thread = None
        self.loop: asyncio.AbstractEventLoop = None
        
        self._init_loop()
        
        if not self.loop.is_running():
            raise RuntimeError("Loop not configured")
        self.loop.create_task(self._publish_changes())

        self.queue = queue or multiprocessing.Queue()
        self._order_books: dict[str, Orderbook] = {
            'BTCUSD': Orderbook(self.loop, 'BTCUSD'),
        }
        self._collection: list[dict] = []
        
    def _init_loop(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._set_loop, daemon=True)
        self.thread.start()

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
            
    def _handle(self, order: dict):
        ob = self._order_books[order['instrument']]
        func: dict[OrderType, callable] = {
            OrderType.MARKET: self._handle_market,
            OrderType.LIMIT: self._handle_limit,
        }[order['order_type']]
        
        result: MatchResult | None = func(order, ob)
        
        if order['order_type'] == OrderType.LIMIT:
            return
        
        if result.outcome == 2:
            order['status'] = OrderStatus.FILLED
            order['standing_quantity'] = order['quantity']
            ob.set_price(result.price)
        else:
            ob.append(order, order['price'])
            if order['standing_quantity'] != order['quantity']:
                order['status'] = OrderStatus.PARTIALLY_FILLED
            
        self._collection.append(order)
    
    def _handle_market(self, order: dict, ob: Orderbook):
        order['price'] = ob.price
        return self._match(order, ob, order['price'])
    
    def _handle_limit(self, order: dict, ob: Orderbook) -> None:
        ob.append(order, order['limit_price'])

    def _match(self, order: dict, ob: Orderbook, price: float) -> MatchResult:
        touched: set[Position] = set()
        filled: set[Position] = set()
        book = 'bids' if order['side'] == Side.SELL else 'asks'
        price: float | None = ob.best_price(order['side'], price)
        
        if price is None:
            return MatchResult(0, None)
        
        if price not in ob[book]:
            return MatchResult(0, None)
        
        for existing_pos in ob[book][price]:
            touched.add(existing_pos)
            leftover_quant = existing_pos.order['standing_quantity'] - order['standing_quantity']
            
            if leftover_quant >= 0:
                existing_pos.order['standing_quantity'] -= order['standing_quantity']
                order['standing_quantity'] = 0
            else:
                filled.add(existing_pos)
                order['standing_quantity'] -= existing_pos.order['standing_quantity']
                existing_pos.order['standing_quantity'] = 0
            
            if order['standing_quantity'] == 0:
                break
        
        self.loop.create_task(self._handle_filled_orders(filled.intersection(touched), ob))
        for p in touched.difference(filled):
            p.order['status'] = OrderStatus.PARTIALLY_FILLED
            self._collection.append(p.order)
        
        if order['standing_quantity'] == 0:
            return MatchResult(2, price)
        
        if order['standing_quantity'] > 0:
            return MatchResult(1, None)
    
    async def _handle_filled_orders(self, pos: Iterable[Position], ob: Orderbook) -> None:
        for p in pos:
            ob.remove(p)
            
            if p.order['status'] == OrderStatus.PARTIALLY_FILLED:
                p.order['status'] = OrderStatus.FILLED
            
        self._collection.extend([p.order for p in pos])

    async def _publish_changes(self) -> None:
        while True:
            if self._collection:
                try:
                    async with get_db_session() as sess:
                        await sess.execute(
                            update(Orders),
                            self._collection
                        )
                        await sess.commit()
                    self._collection.clear()
                except Exception as e:
                    print(f"[futures][publish_changes] => Error: type - ", type(e), "content - ", str(e))
            
            await asyncio.sleep(1.5)