from ..enums import Tag
from enums import Side


class Order:
    """
    Represents an individual order within the order book.

    Each Order has a unique identifier, a tag to classify its
    purpose (e.g., entry, take-profit), a side indicating whether
    it is a bid or ask, a quantity, and an optional price. Tracks
    how much of the order has been filled to support partial executions.
    """

    def __init__(
        self, id_: str, tag: Tag, side: Side, quantity: int, price: float = None
    ) -> None:
        self._id = id_
        self._tag = tag
        self._side = side
        self.quantity = quantity
        self.price = price
        self.filled_quantity = 0

    @property
    def id(self) -> str:
        return self._id

    @property
    def tag(self) -> Tag:
        return self._tag

    @property
    def side(self) -> Side:
        return self._side

    def __eq__(self, value: object) -> bool:
        if issubclass(type(value), Order):
            return self._id == value.id
        raise TypeError(f"Cannot compare {type(value)} and {self.__class__}")

    def __repr__(self) -> str:
        return f"Order(id={self._id}, tag={self._tag}, side={self._side})"
