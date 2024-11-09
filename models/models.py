from typing import Optional

# Local
from enums import OrderStatus

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
