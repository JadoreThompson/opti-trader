from collections import namedtuple
from typing import Literal, TypedDict, Union
from .enums import EnginePayloadCategory


MatchResult = namedtuple(
    "MatchResult",
    (
        "outcome",
        "price",
    ),
)

ClosePayloadQuantity = Union[Literal["ALL"], int]


class EnginePayload(TypedDict):
    """Payload Schema for submitting requests to the engine"""

    category: EnginePayloadCategory
    content: dict


class ClosePayload(TypedDict):
    order_id: str
    quantity: ClosePayloadQuantity


class ModifyPayload(TypedDict):
    order_id: str
    limit_price: float | None = None
    take_profit: float | None = None
    stop_loss: float | None = None
