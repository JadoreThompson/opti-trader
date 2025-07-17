from pydantic import BaseModel, model_validator
from enums import OrderType, Side


class BaseOrder(BaseModel):
    class Config:
        extra = "allow"

    quantity: int
    instrument: str
    order_type: OrderType
    side: Side


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
    limit_price: float


class BaseFuturesOrder(BaseSpotOrder):
    take_profit: float | None = None
    stop_loss: float | None = None


class FuturesMarketOrder(BaseFuturesOrder):
    pass


class FuturesLimitOrder(BaseFuturesOrder):
    limit_price: float


m = BaseOrder(
    quantity=10,
    instrument="a",
    side=Side.ASK,
    order_type=OrderType.LIMIT,
    take_profit=10,
)
print(m.model_extra)
