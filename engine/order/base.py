from datetime import datetime
from .commons import OrderType, OrderStatus

class BaseOrder:
    """Base Order class used to represent an order in the matching engine"""
    
    def __init__(self, data: dict, order_type: OrderType, **kwargs) -> None:
        if isinstance(data['created_at'], str):
            data['created_at'] = datetime.strptime(data['created_at'], "%Y-%m-%d %H:%M:%S.%f")
        
        self.data = data
        self._standing_quantity = data['quantity']
        self._order_status = data['order_status']
        self.order_type = order_type
    
    @property
    def standing_quantity(self):
        return self._standing_quantity
    
    @standing_quantity.setter
    def standing_quantity(self, value: int) -> None:
        self._standing_quantity = value
        self.data['standing_quantity'] = self._standing_quantity
    
    def reduce_standing_quantity(self, value: int):
        self._standing_quantity -= abs(value)
        self.data['standing_quantity'] = self._standing_quantity
        
    @property
    def order_status(self):
        return self._order_status

    @order_status.setter
    def order_status(self, value: OrderStatus):
        self._order_status = self.data['order_status'] = value

        
    def __str__(self) -> str:
        return f"{self.data['order_id'][:5]} >> {self._order_status}"
        
    def __repr__(self):
        return f"{self.data['order_id'][:5]} >> {self._order_status}"
            