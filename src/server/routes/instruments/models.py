from pydantic import BaseModel, field_validator


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

    @field_validator(
        "price", "h24_volume", "h24_change", "h24_high", "h24_low", mode="after"
    )
    def round_two_decimals(cls, v):
        if v is None:
            return v
        return round(float(v), 2)


class OHLC(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float


class InstrumentRead(BaseModel):
    instrument_id: str
    volume: float
    price: float
    h24_change: float | None

    @field_validator("volume", "price", "h24_change")
    def round_values(cls, v):
        if v is not None:
            return round(v, 2)
        return v