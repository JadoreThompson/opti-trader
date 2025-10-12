from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from enums import OrderType, Side, OrderStatus
from models import CustomBaseModel
from server.models import PaginatedResponse


class OrderBase(BaseModel):
    instrument_id: str
    order_type: OrderType
    side: Side
    quantity: float


class OrderCreate(OrderBase):
    limit_price: float | None = Field(None, ge=0)
    stop_price: float | None = Field(None, ge=0)

    @model_validator(mode="before")
    def validate_order_details(cls, values):
        ot = values.get("order_type")

        if ot == OrderType.MARKET.value:
            return values

        if ot == OrderType.LIMIT.value and values.get("limit_price") is None:
            raise ValueError("Must provide limit price for limit orders.")

        if ot == OrderType.STOP.value and values.get("stop_price") is None:
            raise ValueError("Must provide stop price for stop orders.")

        return values


class OCOOrderCreate(BaseModel):
    legs: list[OrderCreate] = Field(min_length=2, max_length=2)

    @field_validator("legs")
    def validate_legs(cls, legs):
        if any(l.order_type == OrderType.MARKET for l in legs):
            raise ValueError("OCO legs cannot be market orders.")

        leg_a, leg_b = legs

        if leg_a.instrument_id != leg_b.instrument_id:
            raise ValueError("OCO legs must be for the same instrument.")
        if leg_a.quantity != leg_b.quantity:
            raise ValueError("OCO legs must have the same quantity.")

        return legs


class OTOOrderCreate(BaseModel):
    parent: OrderCreate
    child: OrderCreate

    @model_validator(mode="after")
    def check_instruments_match(cls, data):
        if data.child.order_type == OrderType.MARKET:
            raise ValueError("OTO child cannot have order_type MARKET.")
        if data.parent.instrument_id != data.child.instrument_id:
            raise ValueError(
                "OTO parent and child orders must be for the same instrument."
            )
        if data.parent.quantity != data.child.quantity:
            raise ValueError("OTO parent and child must have the same quantity.")
        return data


class OTOCOOrderCreate(BaseModel):
    parent: OrderCreate
    oco_legs: list[OrderCreate] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def check_instruments_match(cls, data):
        parent_instrument = data.parent.instrument_id
        quantity = data.parent.quantity
        if any(leg.instrument_id != parent_instrument for leg in data.oco_legs):
            raise ValueError(
                "OTOCO parent and leg orders must be for the same instrument."
            )
        if any(leg.quantity != quantity for leg in data.oco_legs):
            raise ValueError(
                "OTOCO parent and leg orders must be have the same quantity."
            )
        if any(leg.order_type != OrderType.MARKET for leg in data.oco_legs):
            raise ValueError(
                "OTOCO parent and leg orders must be LIMIT or STOP orders."
            )
        return data


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
    limit_price: float | None
    stop_price: float | None
    price: float | None


class PaginatedOrderResponse(PaginatedResponse):
    data: list[OrderRead]
