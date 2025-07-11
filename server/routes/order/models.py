from pydantic import Field, ValidationInfo, field_serializer, field_validator
from typing import Optional
from uuid import UUID

from enums import MarketType, OrderStatus, OrderType, Side
from ...base import CustomBase


class OrderId(CustomBase):
    order_id: str


class OrderWrite(CustomBase):
    quantity: int = Field(..., ge=1)
    instrument: str
    market_type: MarketType
    order_type: OrderType
    side: Side
    limit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    @field_validator("limit_price")
    def validate_limit_price(cls, value: Optional[float]) -> Optional[float]:
        if value:
            return round(value, 2)

    @field_validator("side")
    def validate_tp_sl(cls, value: Side, values: ValidationInfo) -> Side:
        tp = values.data.get("take_profit")
        sl = values.data.get("stop_loss")

        if tp is None and sl is None:
            return value

        if tp == sl:
            raise ValueError("TP and SL cannot have the same value")

        if tp and sl:
            if value == Side.ASK:
                if tp > sl:
                    raise ValueError("SL must be greater than TP")
            if value == Side.BID:
                if sl > tp:
                    raise ValueError("TP must be greater than SL")

        return value

    @field_validator("side")
    def validate_side(cls, value: Side, values: ValidationInfo) -> Side:
        if values.data.get("market_type") == MarketType.SPOT:
            value = Side.BID
        return value


class OrderWriteResponse(CustomBase):
    balance: float  # The new balance after deductions

    @field_serializer("balance")
    def balance_formatter(self, value: float) -> str:
        return f"{round(value, 2):.2f}"


class OrderRead(CustomBase):
    order_id: str
    amount: float
    quantity: int
    instrument: str
    market_type: MarketType
    order_type: OrderType
    side: Side
    status: OrderStatus
    filled_price: Optional[float] = None
    unrealised_pnl: Optional[float] = None
    realised_pnl: Optional[float] = None
    limit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    @field_validator("order_id", mode="before")
    def order_id_validator(cls, value) -> str:
        if isinstance(value, UUID):
            value = str(value)
        return value

    @field_serializer(
        "amount",
        "filled_price",
        "unrealised_pnl",
        "realised_pnl",
        "limit_price",
        "stop_loss",
        "take_profit",
    )
    def formatter_serialiser(self, value) -> Optional[str]:
        if value is not None:
            return f"{round(value, 2):.2f}"
        return value


class PaginatedOrders(CustomBase):
    orders: list[OrderRead]
    has_next_page: bool


class BalancePayload(CustomBase):
    user_id: str
    balance: float

    @field_serializer("balance")
    def balance_serialiser(self, value) -> str:
        return f"{value:.2f}"


class ModifyOrder(CustomBase):
    order_id: str
    limit_price: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None


class FuturesCloseOrder(OrderId):
    pass


class SpotCloseOrder(CustomBase):
    quantity: int = Field(..., ge=1)
    instrument: str
