from enums import OrderType, Side
from ..enums import Tag


class Order:
    """
    Represents an order within the orderbook.
    """

    def __init__(
        self,
        id_: str,
        typ: OrderType,
        tag: Tag,
        side: Side,
        quantity: int,
        price: float | None = None,
    ):
        self._id = id_
        self._tag = tag
        self._type = typ
        self._side = side
        self.price = price
        self.quantity = quantity
        self.filled_quantity = 0

    @property
    def id(self) -> str:
        return self._id

    @property
    def type(self) -> OrderType:
        return self._type

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
        return f"Order(id={self._id}, tag={self._tag}, side={self._side}, quantity={self.quantity}, filled_quantity={self.filled_quantity})"
