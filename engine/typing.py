from collections import namedtuple
from datetime import datetime
from enum import Enum
from typing import Generic, Literal, Protocol, TypeVar, TypedDict, Union, get_type_hints
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
from enums import EventType, OrderType
from utils.utils import get_datetime
from .config import MODIFY_REQUEST_SENTINEL


T = TypeVar("T", bound="EnginePayloadData")


MatchResult = namedtuple(
    "MatchResult",
    ("outcome", "price", "quantity"),
)
Book = Literal["bids", "asks"]
CloseRequestQuantity = Union[Literal["ALL"], int]


class EnginePayloadTopic(Enum):
    CREATE = 0
    CLOSE = 1
    CANCEL = 2
    MODIFY = 3
    APPEND = 4


class EnginePayloadData(BaseModel):
    pass


class EnginePayload(BaseModel, Generic[T]):
    topic: EnginePayloadTopic
    type: OrderType | None = None
    data: T


class OrderEnginePayloadData(EnginePayloadData):
    order: dict


class OCOEnginePayloadData(EnginePayloadData):
    order: dict  # Entry order.
    orders: list[dict] = Field(max_length=2)


class CloseRequest(BaseModel):
    order_id: str


class CancelRequest(CloseRequest):
    pass


class ModifyRequest(BaseModel):
    order_id: str
    limit_price: float | str | None = MODIFY_REQUEST_SENTINEL
    stop_price: float | None = None
    take_profit: float | str | None = MODIFY_REQUEST_SENTINEL
    stop_loss: float | str | None = MODIFY_REQUEST_SENTINEL

    @field_validator("limit_price", "take_profit", "stop_loss")
    def validate_modify_fields(cls, v):
        if isinstance(v, str) and v != MODIFY_REQUEST_SENTINEL:
            raise ValueError(
                "Modify fields must be either a float or the sentinel value '*'."
            )
        return v


class Event(BaseModel):
    event_type: EventType
    user_id: str
    order_id: str
    quantity: int | None = None
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    limit_price: float | None = None
    balance: float | None = None
    asset_balance: int | None = None
    created_at: datetime = Field(default_factory=get_datetime)

    # metadata to help distinguish the order when handlign the event
    # for example {'market_type': MarktType.SPOT} for triggering
    # spot specific logic
    metadata: dict | None = None

    def model_dump(self, *args, **kwargs) -> dict:
        d = super().model_dump(*args, **kwargs)
        return {
            k: (str(v) if isinstance(v, (datetime, UUID)) else v) for k, v in d.items()
        }


class SupportsAppend(Protocol):
    def append(self, *args, **kwargs) -> None: ...
