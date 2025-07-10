import json
from datetime import datetime
from uuid import UUID
from enums import Side
from .enums import Tag


class Order:
    """
    Represents an order within the orderbook

    Attributes:
        current_price_level (Any): The current price level the order is associated with (if any).
        last_touched_price (Any): The most recent price level the order interacted with (if any).
    """

    def __init__(
        self,
        # payload: dict,
        position,
        tag: Tag,
        side: Side,
    ) -> None:
        # self._payload = payload
        self._position = position
        self._tag = tag
        self._side = side
        self.current_price_level = None
        # self.last_touched_price = None

    @property
    def tag(self) -> Tag:
        return self._tag

    @property
    def side(self) -> Side:
        return self._side

    @property
    def position(self) -> "Position":
        return self._position

    # @property
    # def payload(self) -> dict:
    #     return self._payload

    def __eq__(self, other: "Order") -> bool:
        if not isinstance(other, self.__class__):
            raise TypeError(
                f"Cannot perform __eq__ between type {self.__class__} and {type(other)}"
            )

        # return self.payload["order_id"] == value.payload["order_id"] # And user_id?
        return self.position.id == other.position.id

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        # id={self._payload['order_id']},
        # instrument={self._payload['instrument']},
        return f"""Order(
            id={self.position.id}, 
            instrument={self.position.instrument}, 
            side={self._side}, 
            tag={self._tag}, 
            payload={json.dumps(
        {k: (str(v) if isinstance(v, (UUID, datetime)) else v) for k, v in self.position._payload.items()}, indent=4
    )}"""
