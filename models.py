from datetime import date, datetime
from typing import Generic, TypeVar, Union
from pydantic import BaseModel, ValidationError, field_serializer, field_validator
from enums import ClientEventType, EventType, MarketType, InstrumentEventType

T = TypeVar("T")


class ClientEvent(BaseModel):
    event_type: ClientEventType | EventType
    user_id: str
    order_id: str
    data: dict


class PriceUpdate(BaseModel):
    price: float
    market_type: MarketType


class OrderBookSnapshot(BaseModel):
    bids: dict[float, int]
    asks: dict[float, int]


class RecentTrade(BaseModel):
    price: float
    quantity: int
    time: date

    @field_validator("time", mode="before")
    def convert_time(cls, v) -> date:
        if isinstance(v, datetime):
            return datetime.date()
        elif isinstance(v, date):
            return v
        raise ValidationError(f"Invalid type {type(v)} for time")


class SubscriptionRequest(BaseModel):
    subscribe: InstrumentEventType | None = None
    unsubscribe: InstrumentEventType | None = None


class InstrumentEvent(BaseModel, Generic[T]):
    instrument: str
    event_type: InstrumentEventType
    data: T


InstrumentEventUnion = Union[
    InstrumentEvent[OrderBookSnapshot],
    InstrumentEvent[PriceUpdate],
    InstrumentEvent[RecentTrade],
]
