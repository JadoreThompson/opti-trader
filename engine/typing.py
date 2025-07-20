from collections import namedtuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal, TypedDict, Union, get_type_hints
from uuid import UUID
from pydantic import BaseModel, Field

from db_models import get_datetime

MODIFY_DEFAULT = float("inf")

MatchResult = namedtuple(
    "MatchResult",
    ("outcome", "price", "quantity"),
)
Book = Literal["bids", "asks"]
CloseRequestQuantity = Union[Literal["ALL"], int]
BalanceUpdate = namedtuple(
    "BalanceUpdate", ("open_quantity", "standing_quantity", "total_asset_balance")
)


@dataclass
class CloseRequest:
    order_id: str
    quantity: CloseRequestQuantity


@dataclass
class CancelRequest:
    order_id: str
    quantity: CloseRequestQuantity


class ModifyRequest(BaseModel):
    order_id: str
    limit_price: float | None = MODIFY_DEFAULT
    take_profit: float | None = MODIFY_DEFAULT
    stop_loss: float | None = MODIFY_DEFAULT


class PayloadTopic(Enum):
    CREATE = 0
    CLOSE = 1
    CANCEL = 2
    MODIFY = 3
    APPEND = 4


class Payload(BaseModel):
    topic: PayloadTopic
    data: dict


class EventType(str, Enum):
    ASK_SUBMITTED = 'ask_submitted'
    BID_SUBMITTED = 'bid_submitted'
    ORDER_PLACED = "order_placed"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_MODIFIED = "order_modified"
    ORDER_FILLED = "order_filled"
    ORDER_PARTIALLY_FILLED = "order_partially_filled"
    ORDER_REJECTED = "order_rejected"


class Event(BaseModel):
    user_id: str = None
    order_id: str = None
    event_type: str = None
    quantity: int | None = None
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    limit_price: float | None = None
    balance: float | None = None
    asset_balance: int | None = None
    created_at: datetime = Field(default_factory=get_datetime)
    metadata: dict | None = (
        None  # Tag for an order etc. Helps with understanding cash balance direction
    )

    def model_dump(self, *args, **kwargs) -> dict:
        d = super().model_dump(*args, **kwargs)
        return {
            k: (str(v) if isinstance(v, (datetime, UUID)) else v) for k, v in d.items()
        }


def to_typed_dict(typ):
    hints = get_type_hints(Event)
    return TypedDict(f"{typ.__name__}Dict", hints)


EventDict = to_typed_dict(Event)
