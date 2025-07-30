from datetime import datetime
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from engine.typing import MODIFY_SENTINEL, CloseRequestQuantity
from enums import MarketType, OrderStatus, OrderType, Side


MODIFY_ORDER_SENTINEL = float("inf")


class BaseOrder(BaseModel):
    quantity: int = Field(ge=1)
    instrument: str
    order_type: OrderType
    side: Side

    model_config = ConfigDict(extra="allow")


class BaseSpotOCOOrder(BaseOrder):
    take_profit: float | None = Field(None, ge=0)
    stop_loss: float | None = Field(None, ge=0)

    model_config = ConfigDict(extra="forbid")


class SpotMarketOrder(BaseOrder):
    model_config = ConfigDict(extra="forbid")


class SpotMarketOCOOrder(SpotMarketOrder, BaseSpotOCOOrder):
    pass


class SpotLimitOrder(BaseOrder):
    limit_price: float = Field(ge=0)
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def limit_price_validator(self):
        if self.order_type != OrderType.LIMIT:
            raise ValueError("Limit price only allowed for limit orders.")
        if self.limit_price is None:
            raise ValueError("Limit price required for limit orders.")
        return self


class SpotLimitOCOOrder(SpotLimitOrder, BaseSpotOCOOrder):
    @model_validator(mode="after")
    def limit_price_validator(self):
        if self.order_type != OrderType.LIMIT_OCO:
            raise ValueError("Limit price only allowed for limit orders.")
        if self.limit_price is None:
            raise ValueError("Limit price required for limit orders.")
        return self


class BaseFuturesOrder(BaseOrder):
    take_profit: float | None = None
    stop_loss: float | None = None

    model_config = ConfigDict(extra="forbid")


class FuturesMarketOrder(BaseFuturesOrder):
    pass


class FuturesLimitOrder(BaseFuturesOrder):
    limit_price: float

    @field_validator("order_type", mode="after")
    def order_type_validator(cls, v: OrderType) -> OrderType:
        if v != OrderType.LIMIT:
            raise ValueError("Limit price only allowed for limit orders.")

        return v


class ModifyOrder(BaseModel):
    limit_price: float | None = MODIFY_ORDER_SENTINEL
    take_profit: float | None = MODIFY_ORDER_SENTINEL
    stop_loss: float | None = MODIFY_ORDER_SENTINEL

    @field_validator("limit_price", "take_profit", "stop_loss", mode="after")
    def price_validator(cls, v: float | None) -> float | None:
        if v is not None and v < 0.0:
            raise ValueError("Price must be greater than 0.")
        return v


class CancelOrder(BaseModel):
    quantity: CloseRequestQuantity

    @field_validator("quantity", mode="after")
    def quantity_validator(cls, v: CloseRequestQuantity) -> CloseRequestQuantity:
        if not isinstance(v, str) and (v is None or v < 1):
            raise ValueError("Quantity must be greater than 0.")
        return v


class CloseOrder(CancelOrder):
    pass

