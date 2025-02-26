import asyncio
import multiprocessing
import queue

from sqlalchemy import update

from db_models import Orders
from utils.db import get_db_session

from .orderbook import Orderbook
from .position import Position


class FuturesEngine:
    def __init__(self, queue: multiprocessing.Queue = None) -> None:
        self.queue = queue or multiprocessing.Queue()
        self._order_books: dict[str, Orderbook] = {
            'BTCUSD': Orderbook('BTCUSD'),
        }
        self.loop = asyncio.get_event_loop()
        asyncio.set_event_loop(self.loop)
    
    def run(self) -> None:
        while True:
            try:
                message = self.queue.get()
                self._handle(message)
                print("Recevied message: ", message)
            except queue.Empty:
                continue
            
    def _handle(self, order: dict):
        func: dict[str, callable] = {
            'market': self._handle_market,
            'limit': self._handle_limit,
        }[order['order_type']]
        ob = self._order_books[order['instrument']]
        
        result: tuple[int] = func(order, ob)
        print(f"Handling order: {order['order_id']}, result: {result}")
    
    def _handle_market(self, order: dict, ob: Orderbook):
        return self._match(order, ob)
    
    def _handle_limit(self, order: dict, ob: Orderbook) -> None:
        ob.append(order)

    def _match(self, order: dict, ob: Orderbook):
        touched = []
        filled: list[Position] = []
        book = 'bids' if order['side'] == 'sell' else 'asks'
        price = ob.best_price(order['side'], order['price'])
        
        if price is None:
            return (0,)
        
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
            return (2,)
        
        if order['standing_quantity'] > 0:
            ob.append(order)
            return (1,)
        
    
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
            
            