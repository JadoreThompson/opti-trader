from datetime import datetime
from typing import Any
from uuid import uuid4

# SA
from sqlalchemy import Integer, String, UUID, Float, Enum, CheckConstraint, ForeignKey, DateTime, Boolean, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Local
from config import PH
from enums import OrderType, OrderStatus, Side

# Factory Functions
# ^^^^^^^^^^^^^^^^^
def generate_api_key():
    """Generates a hashed UUID4 Key"""
    return PH.hash(str(uuid4()))


def hash_pw(password: str):
    return PH.hash(password)


# Models
# ^^^^^^
class Base(DeclarativeBase):
    pass


class UserWatchlist(Base):
    """Database Model for the user watchilist. Used for copy trading"""
    __tablename__ = 'watchlist_user'
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True),primary_key=True, default=uuid4)
    master: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    watcher: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    limit_orders: Mapped[bool] = mapped_column(Boolean, default=False)
    market_orders: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint('master', 'watcher', name='unq_master_watcher'),
    )

    # users = relationship("Users", back_populates="watchlist_user")
    master_user = relationship("Users", back_populates="watchlist_master", foreign_keys=[master])
    watcher_user = relationship("Users", back_populates="watchlist_watcher", foreign_keys=[watcher])


class Users(Base):
    """Database Model for Users"""
    __tablename__ = "users"

    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=True) # In production remove the nullable clause
    email: Mapped[str] = mapped_column(String, unique=True)
    password: Mapped[str] = mapped_column(String)
    balance: Mapped[float] = mapped_column(Float, default=100000000, nullable=True)
    api_key: Mapped[str] = mapped_column(String, default=generate_api_key)
    visible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    authenticated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    # pfp: Mapped[str] = mapped_column(String)

    # Relationships
    spot_orders = relationship("Orders", back_populates='users', cascade="all, delete-orphan")
    watchlist_master = relationship("UserWatchlist", back_populates="master_user", cascade="all, delete-orphan", foreign_keys=[UserWatchlist.master])
    watchlist_watcher = relationship("UserWatchlist", back_populates="watcher_user", cascade="all, delete-orphan", foreign_keys=[UserWatchlist.watcher])


class Orders(Base):
    """Database Model for Orders"""
    __tablename__ = 'orders'

    # Fields
    order_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        unique=True,
        default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False
    )
    order_status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name='order_status'),
        nullable=True,
        default=OrderStatus.NOT_FILLED
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now
    )
    closed_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True
    )
    ticker: Mapped[str] = mapped_column(
        String
    )
    order_type: Mapped[OrderType] = mapped_column(
        Enum(OrderType, name='order_type')
    )
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )
    price: Mapped[float] = mapped_column(
        Float,
        nullable=True
    )
    filled_price: Mapped[float] = mapped_column(
        Float,
        nullable=True
    )
    limit_price: Mapped[float] = mapped_column(
        Float,
        nullable=True
    )
    take_profit: Mapped[float] = mapped_column(
        Float,
        nullable=True
    )
    stop_loss: Mapped[float] = mapped_column(
        Float,
        nullable=True
    )
    close_price: Mapped[float] = mapped_column(
        Float,
        nullable=True
    )
    standing_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )
    realised_pnl: Mapped[float] = mapped_column(
        Float,
        nullable=True,
        default=0.0
    )
    unrealised_pnl: Mapped[float] = mapped_column(
        Float,
        nullable=True,
        default=0.0
    )

    
    # Constraints
    __tableargs__ = (
        CheckConstraint(quantity > 0, name='quantity_minimum_value'),
        CheckConstraint(take_profit > 0, name='take_profit_minimum_value'),
        CheckConstraint(stop_loss > 0, name='stop_loss_minimum_value'),
        CheckConstraint(limit_price > 0, name='limit_price_minimum_value')
    )

    # Relationships
    users = relationship("Users", back_populates='spot_orders', )

    def __init__(self, **kwargs: Any) -> None:
        kwargs['standing_quantity'] = kwargs['quantity']
        if kwargs['order_type'] == OrderType.LIMIT:
            kwargs['price'] = kwargs['limit_price']
        super().__init__(**kwargs)


# class FuturesContracts(Base):
#     __tablename__ = 'future_contracts'
    
#     side: Mapped[Side] = mapped_column(
#         Enum(Side, name='side'),
#         nullable=False
#     )
#     ticker: Mapped[str] = mapped_column(String, nullable=False)
#     quantity: Mapped[int] = mapped_column(Integer, nullable=False)
#     standing_quantity: Mapped[int] = mapped_column(Integer, nullable=True)
#     limit_price: Mapped[float] = mapped_column(Float, nullable=True)
#     entry_price: Mapped[float] = mapped_column(Float, nullable=True)
#     filled_price: Mapped[float] = mapped_column(Float, nullable=True)
#     stop_loss: Mapped[float] = mapped_column(Float, nullable=True)
#     take_profit: Mapped[float] = mapped_column(Float, nullable=True)
#     unrealised_pnl: Mapped[float] = mapped_column(Float, nullable=True, default=0.0)
#     realised_pnl: Mapped[float] = mapped_column(Float, nullable=True, default=0.0)
#     status: Mapped[OrderStatus] = mapped_column(
#         Enum(OrderStatus, name='order_status'),
#         nullable=True,
#         default=OrderStatus.NOT_FILLED
#     )
    
#     # Relationships
#     users = relationship('Users', back_populates='future_contracts', )
    
#     # Constraints
#     __tableargs__ = (
#         CheckConstraint(quantity > 0, name='quantity_minimum_value'),
#         CheckConstraint(take_profit > 0, name='take_profit_minimum_value'),
#         CheckConstraint(stop_loss > 0, name='stop_loss_minimum_value'),
#         CheckConstraint(limit_price > 0, name='limit_price_minimum_value')
#     )

#     def __init__(self, **kwargs) -> None: 
#         kwargs['standing_quantity'] = kwargs['quantity']
#         super().__init__(**kwargs)


class MarketData(Base):
    """Database Model for Market data"""
    __tablename__ = 'market_data'
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True),primary_key=True, default=uuid4)
    ticker: Mapped[str] = mapped_column(String)
    date: Mapped[int] = mapped_column(Integer, nullable=False, primary_key=True)
    price: Mapped[float] = mapped_column(Float)
    