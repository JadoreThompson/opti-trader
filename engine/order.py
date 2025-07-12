from pydantic import Tag
from enums import Side


class Order:
    """
    Represents an individual order within the order book.

    Each Order has a unique identifier, a tag to classify its
    purpose (e.g., entry, take-profit), a side indicating whether
    it is a buy or sell, a quantity, and an optional price. Tracks
    how much of the order has been filled to support partial executions.
    """

    def __init__(
        self, id_, tag: Tag, side: Side, quantity: int, price: float = None
    ) -> None:
        self._id = id_
        self._tag = tag
        self._side = side
        self.quantity = quantity
        self._price = price
        self.filled_quantity = 0

    @property
    def id(self):
        return self._id

    @property
    def tag(self) -> Tag:
        return self._tag

    @property
    def side(self) -> Side:
        return self._side

    @property
    def price(self) -> float | None:
        return self._price

    def set_price(self, price: float) -> None:
        """
        Sets the price property to `price` if it isn't already set.

        Args:
            price (float): _description_
        """
        if self._price is None:
            self._price = price

    def __eq__(self, value: object) -> bool:
        if isinstance(value, self.__class__):
            return self._id == value.id
        raise TypeError(f"Cannot compare {type(value)} and {self.__class__}")

    def __repr__(self) -> str:
        return f"Order(id={self._id}, tag={self._tag}, side={self._side})"
