from collections import namedtuple
from datetime import datetime
from enum import Enum
from typing import Generic, Literal, Protocol, TypeVar, TypedDict, Union, get_type_hints
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
from enums import EventType, OrderType
from utils.utils import get_datetime
from .config import MODIFY_REQUEST_SENTINEL


E = TypeVar("E", bound="EnginePayloadData")
M = TypeVar("M")


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


class EnginePayload(BaseModel, Generic[E]):
    topic: EnginePayloadTopic
    type: OrderType | None = None
    data: E


class OrderEnginePayloadData(EnginePayloadData):
    order: dict


class OCOEnginePayloadData(EnginePayloadData):
    orders: list[dict]


class OTOEnginePayloadData(EnginePayloadData):
    working_order: dict
    pending_order: dict


class CloseRequest(BaseModel):
    order_id: str


class CancelRequest(CloseRequest):
    pass


class ModifyRequest(Generic[M], BaseModel):
    order_id: str
    data: M


class LimitModifyRequest(BaseModel):
    limit_price: float


class StopModifyRequest(BaseModel):
    stop_price: float = None


class OCOModifyRequest(BaseModel):
    above_price: float = MODIFY_REQUEST_SENTINEL
    below_price: float = MODIFY_REQUEST_SENTINEL


class LegModification(BaseModel):
    limit_price: float = MODIFY_REQUEST_SENTINEL
    stop_price: float = MODIFY_REQUEST_SENTINEL


class OTOModifyRequest(BaseModel):
    working: LegModification | None = None
    pending: LegModification | None = None


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
