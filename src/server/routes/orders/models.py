from uuid import UUID
from datetime import datetime

from pydantic import BaseModel

from enums import OrderType, Side, OrderStatus
from models import CustomBaseModel
from server.models import PaginatedResponse


class OrderBase(BaseModel):
    instrument_id: str
    order_type: OrderType
    side: Side
    quantity: float


class OrderCreate(OrderBase):
    limit_price: float | None = None
    stop_price: float | None = None


class OrderModify(BaseModel):
    limit_price: float | None = None
    stop_price: float | None = None


class OrderRead(OrderBase, CustomBaseModel):
    order_id: UUID
    user_id: UUID
    status: OrderStatus
    executed_quantity: float
    avg_fill_price: float | None = None
    created_at: datetime


class PaginatedOrderResponse(PaginatedResponse):
    data: list[OrderRead]
