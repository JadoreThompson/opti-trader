from typing import Generic, TypeVar, Union
from pydantic import BaseModel, field_serializer
from enums import ClientEventType, EventType, MarketType, InstrumentEventType, Side

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
    side: Side
    time: str

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
