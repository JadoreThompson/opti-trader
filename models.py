from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from enums import OrderType


class Base(BaseModel):
    """Base class for all models with enum value usage enabled."""

    class Config:
        use_enum_values = True


class User(Base):
    """Represents a user with email and password attributes."""

    email: str
    password: str


class TakeProfitOrder(Base):
    price: float = Field(gt=0)


class StopLossOrder(Base):
    price: float = Field(gt=0)


class BaseOrder(Base):
    """Represents a base order with ticker, take profit, and stop loss settings.

    Attributes:
        ticker (str): The symbol of the security.
        take_profit (Optional[float]): The take-profit price, must be positive.
        stop_loss (Optional[float]): The stop-loss price, must be positive.
    """
    ticker: str
    quantity: float = Field(gt=0)
    take_profit: Optional[TakeProfitOrder] = Field(None)
    stop_loss: Optional[StopLossOrder] = Field(None)

    @field_validator('take_profit', check_fields=False)
    def take_profit_validator(cls, take_profit, values) -> float:
        """
        Args:
            take_profit (float): The take-profit price.
            values (dict): The field values of the model.
        Raises:
            ValueError: If stop_loss is greater than or equal to take_profit.
        Returns:
            float: The validated take-profit value.
        """
        stop_loss = values.data.get('stop_loss', None)
        if stop_loss:
            if stop_loss >= take_profit:
                raise ValueError('Stop loss must be less than take profit')
        return take_profit


class MarketOrder(BaseOrder):
    """Represents a market order, inheriting from BaseOrder."""
    pass


class LimitOrder(BaseOrder):
    """Represents a limit order with a specific limit price.

    Attributes:
        limit_price (float): The price at which the limit order is set, must be positive.
    """

    limit_price: float = Field(gt=0)


class CloseOrder(Base):
    order_id: UUID
    quantity: Optional[float] = Field(None, gt=0)


class OrderRequest(Base):
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
