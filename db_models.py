from uuid import uuid4
import sqlalchemy
from sqlalchemy import (
    Float, 
    ForeignKey, 
    UUID, 
    Integer, 
    String
)
from sqlalchemy.orm import (
    DeclarativeBase, 
    Mapped, 
    mapped_column, 
    relationship, 
    validates
)

from config import PH


class Base(DeclarativeBase):
    pass    


class Users(Base):
    __tablename__ = 'users'
    
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String, nullable=False)
    avatar: Mapped[str] = mapped_column(String, nullable=False)
    balance: Mapped[float] = mapped_column(
        Float, 
        nullable=False, 
        default=10000, 
        server_default=sqlalchemy.sql.text('10000')
    )
    
    @validates('password')
    def password_validator(self, _, value):
        return PH.hash(value)
    
    # Relationships
    orders = relationship('Orders', back_populates='users', cascade='all, delete-orphan')


class Orders(Base):
    __tablename__ = 'orders'
    
    order_id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey('users.user_id'))
    instrument: Mapped[str] = mapped_column(String, nullable=False)
    side: Mapped[str] = mapped_column(String, nullable=False)
    market_type: Mapped[str] = mapped_column(String, nullable=False)
    order_type: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default='pending')
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    standing_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    limit_price: Mapped[float] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float] = mapped_column(Float, nullable=True)
    
    # Relationships
    users = relationship('Users', back_populates='orders')
