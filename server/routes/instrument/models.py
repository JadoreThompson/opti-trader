from pydantic import BaseModel
from enum import Enum


class Candle(BaseModel):
    open: float
    high: float
    low: float
    close: float
    time: float


class TimeFrame(Enum):
    S5 = '5s'
    M1 = "1m"
    M5 = "5m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
