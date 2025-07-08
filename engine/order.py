import json
from datetime import datetime
from uuid import UUID
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
        self.current_price_level = None
        self.last_touched_price = None

    @property
    def tag(self) -> Tag:
        return self._tag

    @property
    def side(self) -> Side:
        return self._side

    @property
    def payload(self) -> dict:
        return self._payload

    def __eq__(self, value: "Order") -> bool:
        if not isinstance(value, self.__class__):
            raise TypeError(
                f"Cannot perform __eq__ between type {self.__class__} and {type(value)}"
            )

        return self.payload["order_id"] == value.payload["order_id"] # And user_id?

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"""Order(
            id={self._payload['order_id']}, 
            instrument={self._payload['instrument']}, 
            side={self._side}, 
            tag={self._tag}, 
            payload={json.dumps(
        {k: (str(v) if isinstance(v, (UUID, datetime)) else v) for k, v in self.payload.items()}, indent=4
    )}"""
