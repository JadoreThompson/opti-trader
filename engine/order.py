from enums import Side
from .enums import Tag


class Order:
    def __init__(self, order_data: dict, tag: Tag, side: Side) -> None:
        self._payload = order_data
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
