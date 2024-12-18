import asyncio
from collections import defaultdict
from enum import Enum

from sqlalchemy import update

# Local
from db_models import Orders
from exceptions import DoesNotExist
from utils.db import get_db_session


class OrderManager:
    def __init__(self):
        pass
    
    # class _Keys(int, Enum):
    #     ENTRY = 0
    #     TP = 1
    #     SL = 2
    
    # def _append(self, order) -> None:
    #     self._orders[order.data['order_id']] = order
        
    # def append_entry(self, order):        
    #     self._append(order=order)
    
    # def append_tp(self, order):
    #     self._append(order, "OrderManager._Keys.TP")
        
    # def append_sl(self, order):
    #     self._append(order, "OrderManager._Keys.SL")
    
    # def fetch(self, order_id: str):
    #     try:
    #         return self._orders[order_id]
    #     except KeyError:
    #         raise DoesNotExist('Order')
    
    async def batch_update(self, orders: list[dict]) -> None:
        """
        Performs batch update in the Orders Table
        
        Args:
            orders (list[dict]).
        """        
        # During testing a DBAPIError is thrown since the orders
        # are only generated in memory and not in DB
        async with get_db_session() as session:
            for order in orders:
                try:
                    order.pop('type', None)
                    await session.execute(update(Orders),[order])
                    await session.commit()
                except Exception as e:
                    await session.rollback()
                finally:
                    await asyncio.sleep(0.1)
    