from typing import Optional
from .order import Order


class Position:
    def __init__(self, order: Order) -> None:
        self._instrument = order.order["instrument"]
        self._order = order
        self.stop_loss: Optional[Order] = None
        self.take_profit: Optional[Order] = None

    @property
    def order(self) -> Order:
        return self._order

    @property
    def instrument(self) -> str:
        return self._instrument

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"Position(order=({self.order}), sl=({self.stop_loss}), tp=({self.take_profit}))"
