import asyncio
import pytest
from sqlalchemy import insert, select, update
from db_models import OrderEvents, Orders, Users, get_default_balance
from engine import SpotEngine
from engine.typing import EventType
from enums import MarketType, OrderType, Side
from tests.utils import get_db_sess_async


@pytest.fixture
def engine():
    engine = SpotEngine()
    loop = asyncio.get_event_loop()
    task = loop.create_task(engine.run())

    try:
        yield engine
    finally:
        task.cancel()


@pytest.mark.asyncio(loop_scope="module")
async def test_spot_bid_market_order_integration(
    http_client_authenticated, patched_log, engine
):
    body = {
        "order_type": OrderType.MARKET,
        "quantity": 10,
        "instrument": "BTC",
        "side": Side.BID,
    }

    rsp = await http_client_authenticated.post("/order/spot", json=body)
    data = rsp.json()

    assert rsp.status_code == 201

    async with get_db_sess_async() as sess:
        res = await sess.execute(
            select(OrderEvents).where(OrderEvents.order_id == data["order_id"])
        )
        events = res.scalars().all()

    assert len(events) == 1
    order = events[0]
    assert order.event_type == EventType.ORDER_PLACED
    assert str(order.order_id) == data["order_id"]


@pytest.mark.asyncio(loop_scope="module")
async def test_spot_bid_limit_order_integration(
    http_client_authenticated, patched_log, engine
):
    body = {
        "order_type": OrderType.LIMIT,
        "quantity": 10,
        "instrument": "BTC",
        "side": Side.BID,
        "limit_price": 100.0,
    }

    rsp = await http_client_authenticated.post("/order/spot", json=body)
    data = rsp.json()

    assert rsp.status_code == 201

    async with get_db_sess_async() as sess:
        res = await sess.execute(
            select(OrderEvents).where(OrderEvents.order_id == data["order_id"])
        )
        events = res.scalars().all()

    assert len(events) == 1, [e.event_type for e in events]
    order = events[0]
    assert order.event_type == EventType.ORDER_PLACED
    assert str(order.order_id) == data["order_id"]


@pytest.mark.asyncio(loop_scope="module")
async def test_spot_ask_limit_order_integration(
    http_client_authenticated, patched_log, engine
):
    body = {
        "order_type": OrderType.LIMIT,
        "quantity": 10,
        "instrument": "BTC",
        "side": Side.BID,
        "limit_price": 100.0,
    }

    rsp = await http_client_authenticated.get("/auth/me-id")
    user_id = rsp.json()["user_id"]

    async with get_db_sess_async() as sess:
        res = await sess.execute(
            insert(Orders)
            .values(
                user_id=user_id,
                order_type=body["order_type"],
                market_type=MarketType.SPOT,
                instrument=body["instrument"],
                side=Side.BID,
                standing_quantity=0,
                open_quantity=body["quantity"],
                quantity=body["quantity"],
            )
            .returning(Orders.order_id)
        )
        order_id = res.scalar()

        await sess.execute(update(Users).values(balance=get_default_balance() - 1000.0))

        await sess.execute(
            insert(OrderEvents).values(
                event_type=EventType.ORDER_FILLED,
                user_id=user_id,
                order_id=order_id,
                balance=9000.0,
                asset_balance=10,
            )
        )

    rsp = await http_client_authenticated.post("/order/spot", json=body)
    data = rsp.json()

    assert rsp.status_code == 201

    async with get_db_sess_async() as sess:
        res = await sess.execute(
            select(OrderEvents).where(
                OrderEvents.order_id == data["order_id"],
                OrderEvents.event_type == EventType.ORDER_PLACED,
            )
        )
        events = res.scalars().all()

    assert len(events) == 1