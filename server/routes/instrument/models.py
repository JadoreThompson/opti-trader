from typing import Generic, TypeVar
from pydantic import BaseModel, field_validator
from enum import Enum

from enums import InstrumentEventType


T = TypeVar("T")

class TimeFrame(Enum):
    S5 = "5s"
    M1 = "1m"
    M5 = "5m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


class Candle(BaseModel):
    open: float
    high: float
    low: float
    close: float
    time: float


class InstrumentSummary(BaseModel):
    price: float | None
    change_24h: float | None
    high_24h: float | None
    low_24h: float | None
    volume_24h: float | None

    @field_validator("change_24h", "high_24h", "low_24h", "volume_24h")
    def round_values(cls, v) -> float | None:
        if v is not None:
            return round(v, 2)


class InstrumentStreamMessage(BaseModel, Generic[T]):
    event_type: InstrumentEventType
    data: T