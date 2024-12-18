from .commons import OrderStatus, OrderType
from .base import BaseOrder


class BidOrder(BaseOrder):
    def __init__(self, data: dict, order_type: OrderType, **kwargs) -> None:
        super().__init__(data, order_type, **kwargs)
        
    @property
    def stop_loss(self) -> "None | AskOrder":
        return self._stop_loss_order

    @property
    def take_profit(self) -> "None | AskOrder":
        return self._take_profit_order

    @property
    def order_status(self):
        return self._order_status
    
    @order_status.setter
    def order_status(self, value: OrderStatus) -> None:
        self._order_status = self.data['order_status'] = value
        
        if value == OrderStatus.FILLED:
            self._open_price = self.data['filled_price']
            self.position_size = self.data['quantity'] * self.data['filled_price']

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self):
        return f"BidOrder(order_id={self.data['order_id']})"
            