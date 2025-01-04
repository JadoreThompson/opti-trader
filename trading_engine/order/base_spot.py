from datetime import datetime
from typing import override

from trading_engine.orderbook import OrderBook
from .commons import OrderType, OrderStatus
from .base import Base

class BaseSpotOrder(Base):
    """Base Order class used to represent an order in the matching engine"""
    
    def __init__(self, data: dict, order_type: OrderType, **kwargs) -> None:
        super().__init__(data)
        
        if isinstance(data['created_at'], str):
            data['created_at'] = datetime.strptime(data['created_at'], "%Y-%m-%d %H:%M:%S.%f")
            
        self._standing_quantity = data['quantity']
        self._order_status = data['order_status']
        self._order_type = order_type
        
    def reduce_standing_quantity(self, value: int):
        remaining = self._standing_quantity - value
        
        if remaining <= 0:
            self._standing_quantity = self.data['standing_quantity'] = 0
        else:
            self._standing_quantity = self.data['standing_quantity'] = remaining 

    def __str__(self) -> str:
        return f"{self.data['order_id'][:5]} >> {self._order_status}"
        
    def __repr__(self):
        return f"{self.data['order_id'][:5]} >> {self._order_status}"
    
    @property
    def order_status(self):
        return self._order_status

    @order_status.setter
    def order_status(self, value: OrderStatus):
        self._order_status = self.data['order_status'] = value
        
    @property
    def standing_quantity(self):
        return self._standing_quantity
    
    @standing_quantity.setter
    def standing_quantity(self, value: int) -> None:
        self._standing_quantity = self.data['standing_quantity'] = value
    
    @property
    def order_type(self) -> OrderType:
        return self._order_type
        