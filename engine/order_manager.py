import asyncio
from collections import defaultdict
from enum import Enum

from sqlalchemy import update

# Local
from db_models import Orders
from engine._order import _Order
from exceptions import DoesNotExist
from utils.db import get_db_session
from .config import ASKS, BIDS


class OrderManager:
    def __init__(self):
        self._orders: dict[str, dict] = defaultdict(dict)
    
    class _Keys(int, Enum):
        ENTRY = 0
        TP = 1
        SL = 2
    
    async def _append(self, order: _Order, key: "OrderManager._Keys") -> None:
        self._orders[order.data['order_id']] = order
        
    async def append_entry(self, order: _Order):
        await self._append(order=order, key="OrderManager._Keys.ENTRY")
    
    async def append_tp(self, order: _Order):
        await self._append(order, "OrderManager._Keys.TP")
        
    async def append_sl(self, order: _Order):
        await self._append(order, "OrderManager._Keys.SL")
    
    def _retrieve(self, order_id: str) -> _Order:
        try:
            return self._orders[order_id]
        except KeyError:
            raise DoesNotExist('Order')
    
    def retrieve_entry(self, order_id: str):
        return self._retrieve(order_id)
    
    async def batch_update(self, orders: list[dict]) -> None:
        """
        Performs batch update in the Orders Table
        
        Args:
            orders (list[dict]).
        """        
        
        # During testing due to the orders only being declared 
        # in memory this throws a DBAPIError,
        async with get_db_session() as session:
            for order in orders:
                try:
                    await session.execute(update(Orders),[order])      
                    await session.commit()
                except Exception as e:
                    await session.rollback()
                finally:
                    await asyncio.sleep(0.1)
    
    async def alter_tp_sl(
        self, 
        order_id: str, 
        new_take_profit: float = None, 
        new_stop_loss: float = None
    ) -> None:
        ex_order = self._retrieve(order_id)
        ticker = ex_order.data['ticker']
        
        ex_tp = ex_order.data.get('take_profit', None)
        if ex_tp:
            if ex_order.take_profit in ASKS[ex_order.data['ticker']][ex_tp]:
                ASKS[ticker][ex_tp].remove(ex_order.take_profit)
                ASKS[ticker][new_take_profit].append(ex_order.take_profit)
        
        ex_sl = ex_order.data.get('stop_loss', None)
        if ex_sl:
            if ex_order.stop_loss in ASKS[ex_order.data['ticker']][ex_sl]:
                ASKS[ticker][ex_sl].remove(ex_order.stop_loss)
                ASKS[ticker][new_stop_loss].append(ex_order.stop_loss)
    