from pydantic import BaseModel, Field


class InstrumentCreate(BaseModel):
    instrument_id: str
    symbol: str
    tick_size: float = 1.0


class Stats24h(BaseModel):
    price: float | None
    h24_volume: float
    h24_change: float
    h24_high: float
    h24_low: float


class OHLC(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
