import asyncio
from collections import namedtuple
import multiprocessing
import queue
import threading
import time

from sqlalchemy import update

from db_models import Orders
from enums import OrderStatus, OrderType
from utils.db import get_db_session

from .orderbook import Orderbook
from .position import Position


MatchResult = namedtuple('MatchResult', ('outcome', 'price',))


class FuturesEngine:
    def __init__(self, queue: multiprocessing.Queue = None) -> None:
        self.queue = queue or multiprocessing.Queue()
        self._order_books: dict[str, Orderbook] = {
            'BTCUSD': Orderbook('BTCUSD'),
        }
        self.loop = asyncio.new_event_loop()
        self.collection: list[dict] = []
        self.thread: threading.Thread = None
        
        self._init_loop()
        
        if not self.loop.is_running():
            raise RuntimeError("Loop not configured")
        self.loop.create_task(self._publish_changes())

    def _init_loop(self) -> None:
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
        func: dict[str, callable] = {
            'market': self._handle_market,
            'limit': self._handle_limit,
        }[order['order_type']]
        ob = self._order_books[order['instrument']]
        
        result: MatchResult | None = func(order, ob)
        
        if order['order_type'] == OrderType.LIMIT:
            return
        
        if result.outcome == 2:
            order['status'] = OrderStatus.FILLED
            order['standing_quantity'] = order['quantity']
        elif result.outcome == 1:
            order['status'] = OrderStatus.PARTIALLY_FILLED
        
        self.collection.append(order)
    
    def _handle_market(self, order: dict, ob: Orderbook):
        order['price'] = ob.price
        return self._match(order, ob, order['price'])
    
    def _handle_limit(self, order: dict, ob: Orderbook) -> None:
        ob.append(order)

    def _match(self, order: dict, ob: Orderbook, price: float) -> MatchResult:
        touched = []
        filled: list[Position] = []
        book = 'bids' if order['side'] == 'sell' else 'asks'
        price: float | None = ob.best_price(order['side'], price)
        
        if price is None:
            return MatchResult(0, None)
        
        for existing_pos in ob[book][price]:
            touched.append(existing_pos)
            leftover_quant = existing_pos.order['standing_quantity'] - order['standing_quantity']
            
            if leftover_quant >= 0:
                filled.append(order)
                existing_pos.order['standing_quantity'] -= order['standing_quantity']
                order['standing_quantity'] = 0
            else:
                filled.append(existing_pos)
                order['standing_quantity'] -= existing_pos.order['standing_quantity']
                existing_pos.order['standing_quantity'] = 0
            
            if order['standing_quantity'] == 0:
                break
        
        self.loop.run_until_complete(self._handle_filled_orders(filled, ob))
        
        if order['standing_quantity'] == 0:
            return MatchResult(2, price)
        
        if order['standing_quantity'] > 0:
            ob.append(order)
            return MatchResult(1, None)
    
    async def _handle_filled_orders(self, pos: list[Position], ob: Orderbook):
        for p in pos:
            ob.remove(p)
            p.order['status'] = 'filled'
            
        async with get_db_session() as sess:
            await sess.execute(
                update(Orders),
                [p.order for p in pos]
            )
            
            await sess.commit()

    async def _publish_changes(self) -> None:
        while True:
            if self.collection:
                try:
                    async with get_db_session() as sess:
                        await sess.execute(
                            update(Orders),
                            self.collection
                        )
                        print("Persisting")
                        await sess.commit()
                    self.collection.clear()
                except Exception as e:
                    print(f"[futures][publish_changes] => Error: type - ", type(e), "content - ", str(e))
            
            await asyncio.sleep(1.5)