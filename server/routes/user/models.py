from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
from enums import MarketType, OrderStatus, OrderType, Side


class OrderResponse(BaseModel):
    order_id: str | UUID
    user_id: str | UUID
    closed_at: datetime | None
    instrument: str
    side: Side
    market_type: MarketType
    order_type: OrderType
    price: float | None
    limit_price: float | None
    filled_price: float | None
    closed_price: float | None
    realised_pnl: float = 0.00
    unrealised_pnl: float = 0.00
    status: OrderStatus
    quantity: int
    standing_quantity: int
    open_quantity: int = Field(default=0)
    stop_loss: float | None
    take_profit: float | None
    created_at: datetime

    @field_validator("user_id", "order_id", mode='after')
    def id_to_string(cls, v):
        return str(v)


class OrderQueryParams(BaseModel):
    page: int = Field(default=1, ge=1)
    market_type: list[MarketType] | None = None
    status: list[OrderStatus] | None = None
    order_type: list[OrderType] | None = None
