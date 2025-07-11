from collections import namedtuple
from dataclasses import dataclass
from typing import Literal, Union

MODIFY_DEFAULT = float("inf")

MatchResult = namedtuple(
    "MatchResult",
    ("outcome", "price", "quantity"),
)

CloseRequestQuantity = Union[Literal["ALL"], int]


@dataclass
class CloseRequest:
    order_id: str
    quantity: CloseRequestQuantity

@dataclass
class CancelRequest:
    order_id: str
    quantity: CloseRequestQuantity


@dataclass
class ModifyRequest:
    order_id: str
    limit_price: float | None = MODIFY_DEFAULT
    take_profit: float | None = MODIFY_DEFAULT
    stop_loss: float | None = MODIFY_DEFAULT
