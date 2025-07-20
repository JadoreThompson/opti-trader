from pydantic import BaseModel, ConfigDict, Field, model_validator
from engine.typing import MODIFY_DEFAULT
from enums import OrderType, Side


class BaseOrder(BaseModel):
    quantity: int = Field(ge=1)
    instrument: str
    order_type: OrderType
    side: Side

    model_config = ConfigDict(extra="allow")


class BaseSpotOCOOrder(BaseOrder):
    model_config = ConfigDict(extra="forbid")
    take_profit: float | None = None
    stop_loss: float | None = None


class SpotMarketOrder(BaseOrder):
    model_config = ConfigDict(extra="forbid")


class SpotMarketOCOOrder(SpotMarketOrder):
    pass


class SpotLimitOrder(BaseOrder):
    limit_price: float = Field(ge=0)
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def limit_price_validator(cls, value: "SpotLimitOrder"):
        if value.order_type == OrderType.LIMIT and value.limit_price is None:
            raise ValueError("Limit price required for limit orders.")
        if value.limit_price is not None and value.order_type != OrderType.LIMIT:
            raise ValueError("Limit price allowed only for limit orders.")


class SpotLimitOCOOrder(SpotLimitOrder):
    pass


class BaseFuturesOrder(BaseOrder):
    take_profit: float | None = None
    stop_loss: float | None = None


class FuturesMarketOrder(BaseFuturesOrder):
    pass


class FuturesLimitOrder(BaseFuturesOrder):
    limit_price: float


class ModifyOrder(BaseModel):
    limit_price: float | None = MODIFY_DEFAULT
    take_profit: float | None = MODIFY_DEFAULT
    stop_loss: float | None = MODIFY_DEFAULT
