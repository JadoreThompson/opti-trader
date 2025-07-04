from engine.enums import Tag
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

    def __init__(
        self,
        order: Order,
        stop_loss: Order | None = None,
        take_profit: Order | None = None,
    ) -> None:
        if order.tag != Tag.ENTRY:
            raise ValueError("Order must be of type ENTRY to create a Position.")
        self._instrument = order.payload["instrument"]
        self._entry_order = order
        self.stop_loss_order = stop_loss
        self.take_profit_order = take_profit

    @property
    def entry_order(self) -> Order:
        return self._entry_order

    @property
    def instrument(self) -> str:
        return self._instrument

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"Position(order=({self.entry_order}), sl=({self.stop_loss_order}), tp=({self.take_profit_order}))"
