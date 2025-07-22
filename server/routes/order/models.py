from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from engine.typing import MODIFY_SENTINEL
from enums import OrderType, Side


class BaseOrder(BaseModel):
    quantity: int = Field(ge=1)
    instrument: str
    order_type: OrderType
    side: Side

    model_config = ConfigDict(extra="allow")


class BaseSpotOCOOrder(BaseOrder):

    model_config = ConfigDict(extra="forbid")
    take_profit: float | None = Field(None, ge=0)
    stop_loss: float | None = Field(None, ge=0)


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


class FuturesMarketOrder(BaseFuturesOrder):
    pass


class FuturesLimitOrder(BaseFuturesOrder):
    limit_price: float


class ModifyOrder(BaseModel):
    limit_price: float | None = MODIFY_SENTINEL
    take_profit: float | None = MODIFY_SENTINEL
    stop_loss: float | None = MODIFY_SENTINEL


class CancelOrder(BaseModel):
    quantity: int = Field(ge=1)
