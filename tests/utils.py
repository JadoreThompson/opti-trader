from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator, Generator
from uuid import uuid4

from config import TEST_DB_ENGINE, TEST_DB_ENGINE_ASYNC
from enums import OrderStatus, OrderType, Side
from engine.typing import (
    EnginePayload,
    EnginePayloadTopic,
    OrderEnginePayloadData,
)

smaker = sessionmaker(bind=TEST_DB_ENGINE, class_=Session, expire_on_commit=False)
smaker_async = sessionmaker(
    bind=TEST_DB_ENGINE_ASYNC, class_=AsyncSession, expire_on_commit=False
)


def create_order_dict() -> dict:
    quantity = 1
    return {
        "order_id": str(uuid4()),
        "user_id": str(uuid4()),
        "instrument": "BTC-USD",
        "side": Side.BID,
        "order_type": OrderType.LIMIT,
        "quantity": quantity,
        "standing_quantity": quantity,
        "open_quantity": 0,
        "status": OrderStatus.PENDING,
        "limit_price": None,
        "price": None,
        "take_profit": None,
        "stop_loss": None,
        "filled_price": None,
        "realised_pnl": 0.0,
        "unrealised_pnl": 0.0,
        "closed_at": None,
        "created_at": datetime.now(),
    }


def create_market_limit_data():
    return OrderEnginePayloadData(order=create_order_dict())


def create_engine_payload(ot: OrderType) -> EnginePayload:
    factories = {
        OrderType.MARKET: create_market_limit_data,
        OrderType.LIMIT: create_market_limit_data,
        OrderType.STOP: create_market_limit_data,
    }

    func = factories[ot]
    data = func()
    payload = EnginePayload(topic=EnginePayloadTopic.CREATE, type=ot, data=data)
    return payload


def create_order_simple(
    order_id: str,
    side: Side,
    order_type: OrderType,
    instrument: str = "BTC",
    quantity: int = 10,
    open_quantity: int = 0,
    standing_quantity: int = None,
    limit_price: float | None = None,
    price: float | None = None,
    tp_price: float | None = None,
    sl_price: float | None = None,
) -> dict:
    """A simplified factory for creating test orders."""
    return {
        "order_id": order_id,
        "user_id": str(uuid4()),
        "instrument": instrument,
        "side": side,
        "order_type": order_type,
        "quantity": quantity,
        "standing_quantity": (
            standing_quantity if standing_quantity is not None else quantity
        ),
        "status": OrderStatus.PENDING,
        "limit_price": limit_price,
        "price": price,
        "take_profit": tp_price,
        "stop_loss": sl_price,
        "filled_price": None,
        "realised_pnl": 0.0,
        "unrealised_pnl": 0.0,
        "closed_at": None,
        "created_at": datetime.now(),
        "open_quantity": open_quantity,
    }


def create_order_conditional(i: int, quantity=None) -> dict:
    order_type = OrderType.LIMIT if i % 50 == 0 else OrderType.MARKET
    is_buy = i % 2 == 0
    side = Side.BID if is_buy else Side.ASK
    base_price = 100.0
    limit_price = None

    if order_type == OrderType.LIMIT:
        x = i % 50 + 1
        limit_price = base_price - x if is_buy else base_price + x
        tp_sl_details = {
            "take_profit": limit_price + 20 if is_buy else limit_price - 20,
            "stop_loss": limit_price - 20 if is_buy else limit_price + 20,
        }
    else:
        tp_sl_details = {
            "take_profit": base_price + 20 if is_buy else base_price - 20,
            "stop_loss": base_price - 20 if is_buy else base_price + 20,
        }

    if quantity is None:
        quantity = 10

    order = {
        "order_id": str(i),
        "user_id": str(uuid4()),
        "instrument": "HARNESS_INSTR",
        "side": side,
        "order_type": order_type,
        "quantity": quantity,
        "standing_quantity": quantity,
        "status": OrderStatus.PENDING,
        "realised_pnl": 0.0,
        "unrealised_pnl": 0.0,
        "filled_price": None,
        "limit_price": limit_price,
        "price": None,
        "closed_at": None,
        "closed_price": None,
        "created_at": datetime.now(),
        "amount": 100,
        "open_quantity": 0,
        **tp_sl_details,
    }
    return order


@contextmanager
def get_db_sess() -> Generator[Session, None, None]:
    with smaker() as sess:
        yield sess


async def test_depends_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with smaker_async.begin() as sess:
        yield sess


get_db_sess_async = asynccontextmanager(test_depends_db_session)
