from collections import namedtuple
from dataclasses import dataclass
from typing import Literal, Union

MODIFY_DEFAULT = float("inf")

MatchResult = namedtuple(
    "MatchResult",
    ("outcome", "price", "quantity"),
)
Book = Literal["bids", "asks"]
CloseRequestQuantity = Union[Literal["ALL"], int]
BalanceUpdate = namedtuple("BalanceUpdate", ("open_quantity", "standing_quantity"))


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
