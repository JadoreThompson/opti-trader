from enum import Enum
from typing import Optional
from pydantic import field_serializer
from ...base import CustomBase


class Timeframe(str, Enum):
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"

    def get_seconds(self):
        unit = self.value[-1]
        amount = int(self.value[:-1])

        if unit == "m":
            return amount * 60
        elif unit == "h":
            return amount * 3600
        else:
            raise ValueError(f"Unsupported timeframe unit: {unit}")


class PricePayload(CustomBase):
    price: float
    time: int

    @field_serializer("price")
    def price_serialiser(self, value):
        return f"{value:.2f}"


class OHLC(CustomBase):
    open: float
    high: float
    low: float
    close: float
    time: float


class InstrumentObject(CustomBase):
    name: str
    price: float


class PaginatedInstruments(CustomBase):
    instruments: list[Optional[InstrumentObject]]
    has_next_page: bool
