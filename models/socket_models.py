from datetime import datetime
from pydantic import (
    BaseModel,
    Field,
    field_validator
)
from typing import Optional
from uuid import UUID

from enums import (
    MarketType,
    Side, 
    UpdateScope, 
    OrderType, 
    PubSubCategory
)


class Base(BaseModel):
    """Base class for all models with enum value usage enabled."""
    class Config:
        use_enum_values = True

class _OrderType(Base):
    """Represents the order_type key: value in JSON"""
    type: OrderType


class _MarketType(Base):
    """Represents the market_type key: value in JSON"""
    market_type: MarketType


class TempBaseOrder(_OrderType, _MarketType):
    ticker: str
    quantity: int = Field(gt=0)
    take_profit: Optional[float] = Field(None)
    stop_loss: Optional[float] = Field(None)
    limit_price: Optional[float] = Field(None, gt=0)


class SpotCloseOrder(_MarketType, _OrderType):
    ticker: str
    quantity: Optional[float] = Field(None, gt=0)


class FuturesCloseOrder(_MarketType, _OrderType):
    order_id: str
    quantity: Optional[float] = Field(None, gt=0)


class ModifyOrder(_MarketType, _OrderType):
    order_id: UUID
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None


class FuturesContractWrite(TempBaseOrder):
    """"Core schema for futures contract"""
    side: Side


class FuturesContractRead(FuturesContractWrite):
    standing_quantity: int = Field(ge=0)
    order_id: str
    

class BasePubSubMessage(Base):
    category: PubSubCategory
    message: Optional[str] = None
    details: Optional[dict] = None
    
    @field_validator('details')
    def details_validator(cls, details) -> None:
        if details is not None:
            details = {
                k: (str(v) if isinstance(v, (datetime, UUID)) else v)
                for k, v in details.items()
            }
        return details

class OrderUpdatePubSubMessage(BasePubSubMessage):
    on: UpdateScope
    