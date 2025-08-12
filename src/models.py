from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID
from pydantic import BaseModel

from enums import EventType, InstrumentEventType


class CustomBaseModel(BaseModel):
    model_config = {
        "json_encoders": {
            UUID: lambda x: str(x),
            datetime: lambda x: x.isoformat(),
            Enum: lambda x: x.value,
        }
    }


class InstrumentEvent(BaseModel):
    event_type: InstrumentEventType
    # PriceUpdate | Trade | OrderBookUpdate
    data: Any


class PriceUpdate(BaseModel):
    instrument: str
    price: float


class Trade(BaseModel):
    price: float
    quantity: float
    executed_at: datetime


class OrderBookUpdate(BaseModel):
    # { price: quantity }
    bids: dict[float, float] 
    asks: dict[float, float] 


class OrderUpdate(BaseModel):
    """
    Represents an update to an order, extending the base order dictionary
    with an `event_type` field. Additional unexpected fields are allowed
    for flexibility in handling varied update payloads.
    """

    event_type: EventType
    model_config = {"extra": "allow"}
