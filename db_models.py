from datetime import datetime
from uuid import uuid4

# SA
from sqlalchemy import Integer, String, UUID, Float, Enum, CheckConstraint, ForeignKey, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Local
from config import PH
from enums import OrderType, OrderStatus


def generate_api_key():
    """Generates a hashed UUID4 Key"""
    return PH.hash(str(uuid4()))


class Base(DeclarativeBase):
    pass


class Users(Base):
    __tablename__ = "users"

    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String, unique=True)
    password: Mapped[str] = mapped_column(String)
    balance: Mapped[float] = mapped_column(Float, default=1000000, nullable=True)
    api_key: Mapped[str] = mapped_column(String, default=generate_api_key)

    # Relationships
    orders = relationship("Orders", back_populates='users')


class Orders(Base):
    __tablename__ = 'orders'

    # Fields
    order_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, unique=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    order_status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, name='order_status'), nullable=True, default=OrderStatus.NOT_FILLED)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    closed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    ticker: Mapped[str] = mapped_column(String)
    order_type: Mapped[OrderType] = mapped_column(Enum(OrderType, name='order_type'))
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float, nullable=True)
    filled_price: Mapped[float] = mapped_column(Float, nullable=True)
    limit_price: Mapped[float] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=True)
    close_price: Mapped[float] = mapped_column(Float, nullable=True)

    # Constraints
    __tableargs__ = (
        CheckConstraint(quantity > 0, name='quantity_minimum_value'),
        CheckConstraint(take_profit > 0, name='take_profit_minimum_value'),
        CheckConstraint(stop_loss > 0, name='stop_loss_minimum_value'),
        CheckConstraint(limit_price > 0, name='limit_price_minimum_value')
    )

    # Relationships
    users = relationship("Users", back_populates='orders')


class MarketData(Base):
    __tablename__ = 'market_data'
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True),primary_key=True, default=uuid4)
    ticker: Mapped[str] = mapped_column(String)
    date: Mapped[int] = mapped_column(Integer, nullable=False, primary_key=True)
    price: Mapped[float] = mapped_column(Float)
