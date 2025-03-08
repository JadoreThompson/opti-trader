from typing import Optional
from .order import Order


class Position:
    """
    Represents a trading position. It is used to locate the entry, take profit,
    and stop loss orders from within and outside the order book.

    This class manages the entry order, stop loss order, and take profit order 
    associated with a position.

    Attributes:
        stop_loss (Optional[Order]): The stop loss order for this position, if any.
        take_profit (Optional[Order]): The take profit order for this position, if any.
        instrument (str): The instrument associated with the position.
    """
    def __init__(self, order: Order) -> None:
        self._instrument = order.payload["instrument"]
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
