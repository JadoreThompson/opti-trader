from typing import Any, Optional
from datetime import datetime

# Local
from enums import OrderStatus, OrderType

# Pydantic
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class Base(BaseModel):
    class Config:
        use_enum_values = True
        

class User(Base):
    user_id: UUID


class OrderRequest(User):
    order_status: Optional[OrderStatus] = Field(None, 
                                                description="The specific order status you want the trades to have")
    

class QuantitativeMetrics(BaseModel):
    std: Optional[float] = None
    beta: Optional[float] = None
    sharpe: Optional[float] = None
    treynor: Optional[float] = None
    ahpr: Optional[float] = None
    ghpr: Optional[float] = None
    risk_of_ruin: Optional[float] = None
    
    @field_validator(
        "std", "beta", "sharpe", "treynor",
        "ahpr", "ghpr", "risk_of_ruin",
        mode="before"
    )
    def validator(cls, value):
        if isinstance(value, float):
            value = round(value, 2)
        return value
    

class PerformanceMetrics(QuantitativeMetrics):
    daily: Optional[float | str] = None
    balance: Optional[float | str] = None
    total_profit: Optional[float | str] = None
    winrate: Optional[float | str] = None
    
    
    @field_validator("daily", "balance", "total_profit", "winrate", mode="before")
    def convert_to_float(cls, value, name):
        field = name.field_name
        
        if field in ['daily', 'balance', 'total_profit']:
            chunks = []
            value_list = list(str(value).split('.')[0])
            i = len(value_list)
            
            while i >= 1:
                splitter = i - 3
                if splitter >= 0:
                    chunks.append(value_list[splitter: i])
                else:
                    chunks.append(value_list[0: i])
                i -= 3
            
            value = '$' + ",".join(["".join(chunk) for chunk in chunks[::-1]])
            
        elif field == 'winrate':
            value = f"{value}%"
        
        return value
    

class Order(Base):
    """
    Order Schema for API Endpoints        
    """    
    ticker: str
    order_type: OrderType
    limit_price: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    quantity: float
    order_status: OrderStatus
    price: Optional[float] = None
    created_at: datetime
    filled_price: Optional[float] = None
    closed_at: Optional[datetime] = None
    close_price: Optional[float] = None


class TickerData(BaseModel):
    """
    Ticker data object
    """
    time: Optional[int] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    

class GrowthModel(Base):
    time: int
    value: float
    

class TickerDistribution(Base):
    value: Optional[float] = None
    name: Optional[str] = None
