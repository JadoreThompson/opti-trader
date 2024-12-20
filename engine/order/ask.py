from .commons import OrderStatus, OrderType
from .base import BaseOrder


class AskOrder(BaseOrder):
    def __init__(self, data: dict, order_type: OrderType, **kwargs) -> None:
        super().__init__(data, order_type, **kwargs)

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self):
        return f"AskOrder(order_id={self.data['order_id']})"
    