from enums import Side
from .enums import Tag


class Order:
    """
    Represents a trading order in the system. The order contains information
    about the order data, its side (buy or sell), its associated tag

    Attributes:
        payload (dict): The order data containing the order's details.
        tag (Tag): The tag of the order.
        side (Side): The side of the order, indicating whether it is a buy or sell.
    """

    def __init__(self, payload: dict, tag: Tag, side: Side) -> None:
        self._payload = payload
        self._tag = tag
        self._side = side

    @property
    def tag(self) -> Tag:
        return self._tag

    @property
    def side(self) -> Side:
        return self._side

    @property
    def payload(self) -> dict:
        return self._payload

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"Order(id={self._payload['order_id']}, instrument={self._payload['instrument']}, side={self._side}, tag={self._tag})"
