from typing import Optional
from pydantic import Field, field_validator

from enums import MarketType, OrderType, Side
from ...base import CustomBase

class OrderWrite(CustomBase):
    amount: float
    quantity: int = Field(..., ge=1)
    instrument: str
    market_type: MarketType
    order_type: OrderType
    side: Side
    price: Optional[float]
    limit_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    
    @field_validator('price')
    def validate_price(cls, value):
        return round(value, 2)
    
    @field_validator('limit_price')
    def validate_limit_price(cls, value):
        if value:
            return round(value, 2)
    
    