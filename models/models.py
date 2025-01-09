from typing import List, Optional
from datetime import datetime

# Local
from enums import (
    GrowthInterval, 
    OrderStatus, 
    OrderType,
    MarketType,
    Side,
)

# Pydantic
from uuid import UUID
from pydantic import (
    BaseModel, 
    Field, 
    field_validator, 
    model_validator
)


class Base(BaseModel):
    class Config:
        use_enum_values = True
        

class UserID(Base):
    user_id: UUID


class _User(Base):
    """Represents a user with email and password attributes."""
    email: str
    password: str
    

class LoginUser(_User):
    pass


class RegisterBody(_User):
    username: str


class UserCount(Base):
    count: int
    entities: Optional[list[str]] = Field(
        None, 
        description="A list of usernames"
    )


class UserMetrics(Base):
    following: Optional[UserCount] = None
    followers: UserCount


class Username(Base):
    username: Optional[str] = None


class AuthResponse(Username):
    """Response Model for Login and Register endpoint"""
    token: str
    

class OrderStatusBody(Username):
    order_status: list[OrderStatus]
    

class GrowthBody(Username):
    interval: GrowthInterval


class RetrieveOrdersRequest(UserID):
    order_status: Optional[OrderStatus] = Field(None, 
                    description="The specific order status you want the trades to have")


class QuantitativeMetricsBody(Username):
    benchmark_ticker: Optional[str] = "^GSPC",
    months_ago: Optional[int] = 6,
    total_trades: Optional[int] = 100
    

class QuantitativeMetrics(BaseModel):
    std: Optional[float] = None
    beta: Optional[float] = None
    sharpe: Optional[float] = None
    treynor: Optional[float] = None
    risk_of_ruin: Optional[float] = None
    winrate: Optional[float | str] = None
    
    @field_validator(
        "std", "beta", "sharpe", "treynor",
        "risk_of_ruin", "winrate",
        mode="before"
    )
    def validator(cls, value):
        if isinstance(value, float):
            value = round(value, 2)
        return value
    

class PerformanceMetrics(Base):
    daily: Optional[float | str] = None
    balance: Optional[float | str] = None
    total_profit: Optional[float | str] = None
    std: Optional[float] = None
    beta: Optional[float] = None
    sharpe: Optional[float] = None
    treynor: Optional[float] = None
    risk_of_ruin: Optional[float] = None
    winrate: Optional[float | str] = None
    
    @model_validator(mode='before')
    def validate_fields(cls, values):
        for field, value in values.items():
            values[field] = round(value, 2)
        return values
    
class WinsLosses(Base):
    """
    JSON Schema for the Frontend bar chart showcasing each weekday's gaisn
    """    
    wins: Optional[List[int]] = []
    losses: Optional[List[int]] = []

class SpotOrderRead(Base):
    """Client facing schema for an order"""    
    ticker: str
    market_type: Optional[MarketType] = None
    order_type: OrderType
    limit_price: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    quantity: int
    standing_quantity: int
    order_status: OrderStatus
    price: Optional[float] = None
    created_at: datetime
    filled_price: Optional[float] = None
    closed_at: Optional[datetime] = None
    close_price: Optional[float] = None
    realised_pnl: Optional[float] = 0
    unrealised_pnl: Optional[float] = 0
    order_id: UUID
    

class FuturesContractRead(SpotOrderRead):
    side: Side | str


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
    time: Optional[int] = None
    value: Optional[float] = None
    

class TickerDistribution(Base):
    value: Optional[float] = None
    name: Optional[str] = None


class LeaderboardItem(Base):
    rank: int = Field(gt=0)
    username: str
    earnings: float | str = Field(gt=0)    
    
    @field_validator('earnings')
    def earnings_validator(cls, earnings: float) -> str:
        return f"${round(earnings, 2)}"


class CopyTradeRequest(Base):
    username: str
    spot: bool = False
    futures: bool = False
    limit_order: bool = False
    market_order: bool = False
    
    def __init__(self, **kw):
        if not kw.get('limit_order', None) and not kw.get('market_order', None):
            raise ValueError("Must specifiy either limit_orders or market_orders")
        super().__init__(**kw)
    
    
class ModifyAccountBody(Base):
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    visible: Optional[bool] = None


class RegisterBodyWithToken(RegisterBody):
    token: str