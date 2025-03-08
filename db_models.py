import sqlalchemy

from datetime import datetime
from uuid import uuid4
from sqlalchemy import DateTime, Float, ForeignKey, UUID, Integer, String
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    validates,
)

from config import PH


class Base(DeclarativeBase):
    pass


class Users(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String, nullable=False)
    avatar: Mapped[str] = mapped_column(String, nullable=False)
    balance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=10000,
        server_default=sqlalchemy.sql.text("10000"),
    )

    @validates("password")
    def password_validator(self, _, value):
        return PH.hash(value)

    # Relationships
    orders = relationship(
        "Orders", back_populates="users", cascade="all, delete-orphan"
    )


class Orders(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    instrument: Mapped[str] = mapped_column(String, nullable=False)
    side: Mapped[str] = mapped_column(String, nullable=False)
    market_type: Mapped[str] = mapped_column(String, nullable=False)
    order_type: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=True)
    limit_price: Mapped[float] = mapped_column(Float, nullable=True)
    filled_price: Mapped[float] = mapped_column(Float, nullable=True)
    closed_price: Mapped[float] = mapped_column(Float, nullable=True)
    realised_pnl: Mapped[float] = mapped_column(Float, nullable=True, default=0)
    unrealised_pnl: Mapped[float] = mapped_column(Float, nullable=True, default=0)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    standing_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float] = mapped_column(Float, nullable=True)

    # Relationships
    users = relationship("Users", back_populates="orders")


class MarketData(Base):
    __tablename__ = "market_data"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    instrument: Mapped[str] = mapped_column(String, nullable=False)
    time: Mapped[int] = mapped_column(Integer, nullable=False, default=datetime.now)
    price: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
