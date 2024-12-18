from .commons import OrderStatus, OrderType
from .base import BaseOrder


class AskOrder(BaseOrder):
    def __init__(self, data: dict, order_type: OrderType, **kwargs) -> None:
        super().__init__(data, order_type, **kwargs)

    @property
    def order_status(self):
        return self._order_status
    
    @order_status.setter
    def order_status(self, value: OrderStatus):
        self._order_status = self.data['order_status'] = value

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self):
        return f"AskOrder(order_id={self.data['order_id']})"
    