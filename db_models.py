import sqlalchemy

from datetime import datetime, UTC
from uuid import uuid4
from sqlalchemy import DateTime, Float, ForeignKey, UUID, Integer, String
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    validates,
)
from enums import OrderStatus


def get_datetime() -> datetime:
    return datetime.now(UTC)


def get_default_user_balance() -> float:
    return 10_000


class Base(DeclarativeBase):
    def dump(self, exclude: list[str] | None = None) -> dict:
        """
        Converts a SQLAlchemy object to a dictionary. Excluding
        the keys passed in `exclude`.

        Args:
            exclude (list[str], optional): Keys to exclude in the dictionary. Defaults to None.

        Returns:
            dict: Dictionary representation of self's properties.
        """
        if exclude is None:
            exclude = []
        exclude.append("_sa_instance_state")
        return {k: v for k, v in vars(self).items() if k not in exclude}


class Users(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    password: Mapped[str] = mapped_column(String, nullable=False)
    avatar: Mapped[str | None] = mapped_column(String, nullable=True)
    balance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=10000,
        server_default=sqlalchemy.sql.text(f"{get_default_user_balance()}"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_datetime, nullable=False
    )

    # Relationships
    orders = relationship(
        "Orders", back_populates="users", cascade="all, delete-orphan"
    )
    order_events = relationship("OrderEvents", back_populates="user")
    escrows = relationship(
        "Escrows", back_populates="user", cascade="all, delete-orphan"
    )


class Orders(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id")
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    instrument: Mapped[str] = mapped_column(String, nullable=False)
    side: Mapped[str] = mapped_column(String, nullable=False)
    market_type: Mapped[str] = mapped_column(String, nullable=False)
    order_type: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    filled_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    closed_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    realised_pnl: Mapped[float | None] = mapped_column(Float, nullable=True, default=0)
    unrealised_pnl: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=0
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=OrderStatus.PENDING.value
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    standing_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    open_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=sqlalchemy.sql.text("0")
    )
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_datetime, nullable=False
    )

    # Relationships
    users = relationship("Users", back_populates="orders")
    order_events = relationship("OrderEvents", back_populates="order")
    escrow = relationship(
        "Escrows", back_populates="order", cascade="all, delete-orphan"
    )


class MarketData(Base):
    __tablename__ = "market_data"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    instrument: Mapped[str] = mapped_column(String, nullable=False)
    instrument_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("instruments.instrument_id"),
        nullable=False,
    )
    time: Mapped[int] = mapped_column(Integer, nullable=False, default=datetime.now)
    price: Mapped[float] = mapped_column(Float, nullable=False)

    # Relationship
    instruments_relationship = relationship(
        "Instruments", back_populates="market_data_relationship"
    )


class Instruments(Base):
    __tablename__ = "instruments"

    instrument_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        unique=True,
    )
    instrument: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    starting_price: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_datetime, nullable=False
    )

    # Relationship
    market_data_relationship = relationship(
        MarketData,
        back_populates="instruments_relationship",
        cascade="all, delete-orphan",
    )


class OrderEvents(Base):
    __tablename__ = "order_events"

    order_event_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    order_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.order_id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    balance: Mapped[float] = mapped_column(Float, nullable=False)  # Acc balance
    asset_balance: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_datetime, nullable=False
    )

    # Relationships
    user = relationship("Users", back_populates="order_events")
    order = relationship("Orders", back_populates="order_events")


class Escrows(Base):
    __tablename__ = "escrows"

    escrow_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    order_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.order_id"), nullable=False
    )
    balance: Mapped[float] = mapped_column(Float, nullable=False)

    # Relationships
    user = relationship("Users", back_populates="escrows")
    order = relationship("Orders", back_populates="escrow")
