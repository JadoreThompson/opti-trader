from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, field_validator

from enums import EventType, InstrumentEventType, Side


class CustomBaseModel(BaseModel):
    model_config = {
        "json_encoders": {
            UUID: lambda x: str(x),
            datetime: lambda x: x.isoformat(),
            Enum: lambda x: x.value,
        }
    }


class InstrumentEvent(CustomBaseModel):
    event_type: InstrumentEventType
    instrument_id: str
    # PriceEvent | TradeEvent | OrderBookSnapshot
    data: Any


class PriceEvent(BaseModel):
    price: float


class TradeEvent(CustomBaseModel):
    price: float
    quantity: float
    side: Side
    executed_at: datetime

    @field_validator("price", "quantity")
    def round_values(cls, v):
        return round(v, 2)


class OrderBookSnapshot(BaseModel):
    # { price: quantity }
    bids: dict[float, float]
    asks: dict[float, float]


class OrderEvent(CustomBaseModel):
    """Event emitted on a fill, place, cancel of an order."""

    event_type: EventType
    available_balance: float
    data: dict[str, Any]  # order dictionary
