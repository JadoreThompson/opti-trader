from typing import Any, Optional
from pydantic import Field, ValidationInfo, field_validator

from api.routes.order.enums import SocketPayloadCategory
from enums import MarketType, OrderType, Side
from ...base import CustomBase


class OrderWrite(CustomBase):
    amount: float
    quantity: int = Field(..., ge=1)
    instrument: str
    market_type: MarketType
    order_type: OrderType
    side: Side
    limit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    @field_validator('limit_price')
    def validate_limit_price(cls, value):
        if value:
            return round(value, 2)
    
    @field_validator('side')
    def tp_sl_validator(cls, value: Side, values: ValidationInfo):
        tp = values.data.get('take_profit')
        sl = values.data.get('stop_loss')
        
        if tp is None and sl is None:
            return value
        
        if tp == sl:
            raise ValueError("TP and SL cannot have the same value")
        
        if tp and sl:
            if value == Side.SELL:
                if tp > sl:
                    raise ValueError("SL must be greater than TP")
            if value == Side.BUY:
                if sl > tp:
                    raise ValueError("TP must be greater than SL")
                
        return value


class OrderRead(CustomBase):
    order_id: str
    amount: float
    quantity: int
    instrument: str
    market_type: MarketType
    order_type: OrderType
    side: Side
    limit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    

class PricePayload(CustomBase):
    price: float
    time: int


class ConnectPayload(CustomBase):
    instrument: str


class SocketPayload(CustomBase):
    """Used for both posting and receiving messages"""
    category: SocketPayloadCategory
    content: dict