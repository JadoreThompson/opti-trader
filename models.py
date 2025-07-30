from datetime import date, datetime
from pydantic import BaseModel, ValidationError, field_validator
from enums import ClientEventType, EventType, MarketType, StreamEventType


class ClientEvent(BaseModel):
    event_type: ClientEventType | EventType
    user_id: str
    order_id: str
    data: dict


class PriceUpdate(BaseModel):
    instrument: str
    price: float
    market_type: MarketType


class OrderBookStream(BaseModel):
    bids: dict[float, int]
    asks: dict[float, int]


class OrderBookSnapshot(OrderBookStream):
    instrument: str


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


class StreamRequest(BaseModel):
    subscribe: StreamEventType | None = None
    unsubscribe: StreamEventType | None = None


class StreamEvent(BaseModel):
    event_type: StreamEventType
    data: PriceUpdate | OrderBookStream | RecentTrade
