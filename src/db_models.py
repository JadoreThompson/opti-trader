from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    UUID as SAUUID,
    Float,
    ForeignKey,
    String,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

from enums import InstrumentStatus, UserStatus, OrderStatus
from utils.utils import get_datetime, get_default_cash_balance


class Base(DeclarativeBase):
    def dump(self) -> dict:
        return {k: v for k, v in vars(self).items() if k != "_sa_instance"}


class Users(Base):
    __tablename__ = "users"

    user_id: Mapped[UUID] = mapped_column(
        SAUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    cash_balance: Mapped[float] = mapped_column(
        Float, nullable=False, default=get_default_cash_balance
    )
    escrow_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.00)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=UserStatus.ACTIVE.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=get_datetime
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=get_datetime,
        onupdate=get_datetime,
    )

    orders = relationship("Orders", back_populates="user", cascade="all, delete-orphan")
    trades = relationship("Trades", back_populates="user", cascade="all, delete-orphan")
    events = relationship("Events", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship(
        "Transactions", back_populates="user", cascade="all, delete-orphan"
    )
    asset_balances = relationship(
        "AssetBalances", back_populates="user", cascade="all, delete-orphan"
    )


class Instruments(Base):
    __tablename__ = "instruments"

    instrument_id: Mapped[str] = mapped_column(
        String(50), primary_key=True, nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    tick_size: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=InstrumentStatus.TRADABLE.value
    )

    orders = relationship(
        "Orders", back_populates="instrument", cascade="all, delete-orphan"
    )
    trades = relationship(
        "Trades", back_populates="instrument", cascade="all, delete-orphan"
    )
    asset_balances = relationship(
        "AssetBalances", back_populates="instrument", cascade="all, delete-orphan"
    )


class Orders(Base):
    __tablename__ = "orders"

    order_id: Mapped[UUID] = mapped_column(
        SAUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        SAUUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    instrument_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("instruments.instrument_id"), nullable=False
    )
    side: Mapped[str] = mapped_column(String, nullable=False)  # from Side enum .value
    order_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # from OrderType enum .value
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    executed_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_fill_price: Mapped[float] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=OrderStatus.PENDING.value
    )
    time_in_force: Mapped[str] = mapped_column(
        String, nullable=True
    )  # from TimeInForce enum .value
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=get_datetime
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=get_datetime,
        onupdate=get_datetime,
    )

    user = relationship("Users", back_populates="orders")
    instrument = relationship("Instruments", back_populates="orders")
    trades = relationship(
        "Trades", back_populates="order", cascade="all, delete-orphan"
    )


class Trades(Base):
    __tablename__ = "trades"

    trade_id: Mapped[UUID] = mapped_column(
        SAUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    order_id: Mapped[UUID] = mapped_column(
        SAUUID(as_uuid=True), ForeignKey("orders.order_id"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        SAUUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    instrument_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("instruments.instrument_id"), nullable=False
    )
    price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    liquidity: Mapped[str] = mapped_column(
        String, nullable=False
    )  # from LiquidityRole enum .value
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=get_datetime
    )

    order = relationship("Orders", back_populates="trades")
    user = relationship("Users", back_populates="trades")
    instrument = relationship("Instruments", back_populates="trades")


class AssetBalances(Base):
    __tablename__ = "asset_balances"

    user_id: Mapped[UUID] = mapped_column(
        SAUUID(as_uuid=True), ForeignKey("users.user_id"), primary_key=True
    )
    instrument_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("instruments.instrument_id"), primary_key=True
    )
    balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.00)
    escrow_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.00)

    user = relationship("Users", back_populates="asset_balances")
    instrument = relationship("Instruments", back_populates="asset_balances")


class Events(Base):
    __tablename__ = "events"

    event_id: Mapped[UUID] = mapped_column(
        SAUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    event_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # from EventsType enum .value
    user_id: Mapped[UUID] = mapped_column(
        SAUUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    related_id: Mapped[str] = mapped_column(
        # String(50), nullable=True
        SAUUID(as_uuid=True),
        nullable=False,
    )  # Could be order_id, trade_id, etc.
    details: Mapped[str] = mapped_column(Text, nullable=True)  # JSON string
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=get_datetime
    )

    user = relationship("Users", back_populates="events")


class Transactions(Base):
    __tablename__ = "transactions"

    transaction_id: Mapped[UUID] = mapped_column(
        SAUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        SAUUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # from TransactionType enum .value
    related_id: Mapped[str] = mapped_column(
        String(50), nullable=True
    )  # Could be trade_id, deposit_id, etc.
    balance: Mapped[float] = mapped_column(
        Float, nullable=False
    )  # Cash balance after transaction
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=get_datetime
    )

    user = relationship("Users", back_populates="transactions")
