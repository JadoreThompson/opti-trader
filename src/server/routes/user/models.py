from datetime import datetime
from typing import Literal, TypeAlias
from pydantic import BaseModel, field_validator


HistoryInterval: TypeAlias = Literal["1d", "1w", "1m", "3m", "6m", "1y"]


class UserOverviewResponse(BaseModel):
    cash_balance: float
    portfolio_balance: float
    data: dict[str, float]  # { BTC-USD: 100 }


class PortfolioHistory(BaseModel):
    time: datetime
    value: float

    @field_validator("value")
    def round_value(cls, v):
        return round(v, 2)
