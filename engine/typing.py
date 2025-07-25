from collections import namedtuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from multiprocessing import Queue as MPQueue
from typing import Literal, Protocol, TypedDict, Union, get_type_hints
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
from db_models import get_datetime


MatchResult = namedtuple(
    "MatchResult",
    ("outcome", "price", "quantity"),
)
Book = Literal["bids", "asks"]

CloseRequestQuantity = Union[Literal["ALL"], int]
MODIFY_SENTINEL = "*"


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
    limit_price: float | str | None = MODIFY_SENTINEL
    take_profit: float | str | None = MODIFY_SENTINEL
    stop_loss: float | str | None = MODIFY_SENTINEL

    @field_validator("limit_price", "take_profit", "stop_loss")
    def validate_modify_fields(cls, v):
        if isinstance(v, str) and v != "*":
            raise ValueError(
                "Modify fields must be either a float or the sentinel value '*'."
            )
        return v


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
    ASK_SUBMITTED = "ask_submitted"
    BID_SUBMITTED = "bid_submitted"
    ORDER_NEW = "order_new"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_MODIFIED = "order_modified"
    ORDER_PARTIALLY_FILLED = "order_partially_filled"
    ORDER_FILLED = "order_filled"
    ORDER_PARTIALLY_CLOSED = "order_partially_closed"
    ORDER_CLOSED = "order_closed"
    ORDER_REJECTED = (
        "order_rejected"  # Backwards compatibility, use ORDER_NEW_REJECTED instead
    )
    ORDER_NEW_REJECTED = "order_new_rejected"
    ORDER_PARTIALLY_CANCELLED = "order_partially_cancelled"
    ORDER_CANCEL_REJECTED = "order_cancel_rejected"
    ORDER_MODIFY_REJECTED = "order_modify_rejected"


class Event(BaseModel):
    user_id: str | None = None
    order_id: str | None = None
    event_type: str | None = None
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


############### Queue ###############
class Queue:
    def __init__(self):
        self._queue = MPQueue()

    def _dump_dict(self, obj: dict):
        for k, v in obj.items():
            if isinstance(v, dict):
                obj[k] = self._dump_dict(v)
            elif isinstance(v, (UUID, datetime)):
                obj[k] = str(v)
            elif isinstance(v, Enum):
                obj[k] = v.value

        return obj

    def append(self, obj: object):
        if isinstance(obj, dict):
            obj = self._dump_dict(obj)
        return self._queue.put(obj)

    def get(self, *args, **kwargs):
        return self._queue.get(*args, **kwargs)

    def size(self):
        return self._queue.qsize()


class SupportsAppend(Protocol):
    def append(self, *args, **kwargs) -> None: ...


############### Dicts of Types ###############
def to_typed_dict(typ):
    hints = get_type_hints(typ)
    return TypedDict(f"{typ.__name__}Dict", hints)


EventDict = to_typed_dict(Event)
