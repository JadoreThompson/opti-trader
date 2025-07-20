from pydantic import BaseModel, ConfigDict, Field, model_validator
from enums import OrderType, Side


class BaseOrder(BaseModel):
    quantity: int = Field(ge=1)
    instrument: str
    order_type: OrderType
    side: Side

    model_config = ConfigDict(extra="allow")


class BaseSpotOrder(BaseOrder):
    take_profit: float | None = None
    stop_loss: float | None = None

    @model_validator(mode="after")
    def tp_sl_validator(cls, value: "SpotMarketOrder"):
        if value.side == Side.ASK:
            if value.take_profit is not None or value.stop_loss is not None:
                raise ValueError("Cannot set TP or SL on sell order.")
        return value


class SpotMarketOrder(BaseSpotOrder):
    pass


class SpotLimitOrder(BaseSpotOrder):
    limit_price: float = Field(ge=0)

    @model_validator(mode="after")
    def limit_price_validator(cls, value: "SpotLimitOrder"):
        if value.order_type == OrderType.LIMIT and value.limit_price is None:
            raise ValueError("Limit price required for limit orders.")
        if value.limit_price is not None and value.order_type != OrderType.LIMIT:
            raise ValueError("Limit price allowed only for limit orders.")


class BaseFuturesOrder(BaseSpotOrder):
    take_profit: float | None = None
    stop_loss: float | None = None


class FuturesMarketOrder(BaseFuturesOrder):
    pass


class FuturesLimitOrder(BaseFuturesOrder):
    limit_price: float
