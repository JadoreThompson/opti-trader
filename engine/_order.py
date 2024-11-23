from datetime import datetime
from enums import _OrderType, OrderStatus


class _Order:
    """
    This class represents an order
    and some of  the properties to be used
    by the matching engine and order manager
    for retrieval and later computation
    """
    
    def __init__(self, data: dict, order_type: _OrderType) -> None:
        if isinstance(data['created_at'], str):
            data['created_at'] = datetime.strptime(data['created_at'], "%Y-%m-%d %H:%M:%S.%f")
        
        self.data = data
        self._quantity = data['quantity']
        self._standing_quantity = data['quantity']
        self._order_status = data['order_status']
        
        self._close_price = None
        self._open_price = None
        self.order_type = order_type
    
    @property
    def quantity(self):
        return self._quantity
        
    @property
    def close_price(self):
        return self._close_price
    
    @close_price.setter
    def close_price(self, value: float):
        self._close_price = value
    
    @property
    def open_price(self) -> float | None:
        return self._open_price

    @open_price.setter
    def open_price(self, value: float) -> None:
        self._open_price = value
    
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
    def order_status(self, value: OrderStatus) -> None:
        self._order_status = value
        self.data['order_status'] = self._order_status
    
    def list(self) -> list:
        return [self.quantity, self.data]
        
    def __str__(self) -> str:
        return f"{self.data['order_id'][:5]} >> {self.order_status}"
        
    def __repr__(self):
        return f"{self.data['order_id'][:5]} >> {self.order_status}"
