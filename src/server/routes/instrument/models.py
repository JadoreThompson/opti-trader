from pydantic import BaseModel


class InstrumentCreate(BaseModel): ...


class OHLC(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
