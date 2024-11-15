from typing import Optional
from datetime import datetime

# Local
from enums import OrderStatus, OrderType

# Pydantic
from uuid import UUID
from pydantic import BaseModel, Field


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
    

class PerformanceMetrics(QuantitativeMetrics):
    daily: Optional[float] = None
    balance: Optional[float] = None
    total_profit: Optional[float] = None
    winrate: Optional[float] = None


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


class TickerData(Base):
    """
    Ticker data object 
    """
    time: int    
    open: float
    high: float
    low: float
    close: float
    

class GrowthModel(Base):
    time: int
    value: float
    

class TickerDistribution(Base):
    value: float
    name: str
