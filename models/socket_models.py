from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from pydantic import (
    BaseModel,
    Field,
    field_validator
)

from enums import (
    MarketType,
    OrderStatus,
    Side, 
    UpdateScope, 
    OrderType, 
    PubSubCategory
)


class Base(BaseModel):
    """Base class for all models with enum value usage enabled."""
    class Config:
        use_enum_values = True

# New
class _OrderType(Base):
    """Represents the order_type key: value in JSON"""
    type: OrderType


class _MarketType(Base):
    """Represents the market_type key: value in JSON"""
    market_type: MarketType


class TakeProfit(Base):
    price: float = Field(gt=0)


class StopLoss(Base):
    price: float = Field(gt=0)
    

class BaseOrder(Base):
    """Represents a base order with ticker, take profit, and stop loss settings.

    Attributes:
        ticker (str): The symbol of the security.
        take_profit (Optional[float]): The take-profit price, must be positive.
        stop_loss (Optional[float]): The stop-loss price, must be positive.
    """
    ticker: str
    quantity: int = Field(gt=0)
    take_profit: Optional[TakeProfit] = Field(None)
    stop_loss: Optional[StopLoss] = Field(None)


## New
class TempBaseOrder(_OrderType, _MarketType):
    ticker: str
    quantity: int = Field(gt=0)
    take_profit: Optional[TakeProfit] = Field(None)
    stop_loss: Optional[StopLoss] = Field(None)
    limit_price: Optional[float] = Field(None, gt=0)


class MarketOrder(BaseOrder):
    """Represents a spot market order"""
    @field_validator('take_profit', check_fields=False)
    def take_profit_validator(cls, take_profit, values) -> float:
        stop_loss = values.data.get('stop_loss', None)
        
        try:    
            if stop_loss and take_profit:
                if take_profit.price <= stop_loss.price:
                    raise ValueError('Take profit price must be greater than stop loss price')
        except AttributeError:
            pass
        finally:
            return take_profit


class LimitOrder(BaseOrder):
    """Represents a spot limit order"""

    limit_price: float = Field(gt=0)
    
    @field_validator('limit_price', check_fields=False)
    def limit_price_validator(cls, limit_price: float, values):
        stop_loss = values.data.get('stop_loss', None)
        take_profit = values.data.get('take_profit', None)
        
        if stop_loss:
            if stop_loss.price >= limit_price:
                raise ValueError('Stop Loss must be greater than limit price')
        if take_profit:
            if take_profit.price <= limit_price:
                raise ValueError('Take profit must be greater than limit price')
        return limit_price


class CloseOrder(_MarketType):
    ticker: str
    quantity: Optional[float] = Field(None, gt=0)


class ModifyOrder(Base):
    order_id: UUID
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None


class EntryPriceChange(Base):
    price: float
    order_id: UUID


class Request(Base):
    """Represents an order with type, market order, and limit order details.

    Attributes:
        type (OrderType): The type of the order (e.g., market or limit).
        market_order (Optional[MarketOrder]): Details of the market order, if applicable.
        limit_order (Optional[LimitOrder]): Details of the limit order, if applicable.
    """
    type: OrderType
    market_order: Optional[MarketOrder] = None
    limit_order: Optional[LimitOrder] = None
    close_order: Optional[CloseOrder] = None
    modify_order: Optional[ModifyOrder] = None


class SpotOrderWrite(TempBaseOrder):
    pass


class FuturesContractWrite(TempBaseOrder):
    """"Core schema for futures contract"""
    side: Side


class FuturesContractRead(FuturesContractWrite):
    standing_quantity: int = Field(ge=0)


class TradeRequest(Base):
    market_type: MarketType
    spot: Optional[Request] = None
    futures: Optional[FuturesContractWrite] = None

    @field_validator('spot', check_fields=False)
    def spot_validator(cls, value):
        print(value)
    

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
    
    