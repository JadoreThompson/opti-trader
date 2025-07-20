import pytest

from sqlalchemy import insert, select, update
from config import REDIS_CLIENT
from db_models import Escrows, OrderEvents, Orders, Users, get_default_balance
from engine.typing import EventType
from enums import MarketType, OrderType, Side
from tests.utils import get_db_sess_async


@pytest.mark.asyncio(loop_scope="module")
async def test_create_spot_bid_market_order(http_client_authenticated):
    instrument = "test-ticker"

    await REDIS_CLIENT.set(instrument, 100.0)

    body = {
        "order_type": OrderType.MARKET,
        "quantity": 10,
        "instrument": instrument,
        "side": Side.BID,
    }

    rsp = await http_client_authenticated.post("/order/spot", json=body)
    data = rsp.json()

    assert rsp.status_code == 201, vars(rsp)
    assert len(data) == 1
    assert "order_id" in data

    async with get_db_sess_async() as sess:
        orders = await sess.execute(
            select(Orders).where(Orders.order_id == data["order_id"])
        )
        orders = orders.scalars().all()

        escrow_balance = await sess.execute(
            select(Escrows.balance).where(Escrows.order_id == data["order_id"])
        )
        escrow_balance = escrow_balance.scalar()
        user_balance = await sess.execute(
            select(Users.balance).where(
                Users.user_id
                == select(Orders.user_id)
                .where(Orders.order_id == data["order_id"])
                .scalar_subquery()
            )
        )
        user_balance = user_balance.scalar()

    assert len(orders) == 1
    order = orders[0]
    assert order.instrument == body["instrument"]
    assert order.quantity == body["quantity"]
    assert order.side == body["side"]
    assert order.order_type == body["order_type"]
    assert escrow_balance == 1000.0
    assert user_balance == get_default_balance() - 1000.0


@pytest.mark.asyncio(loop_scope="module")
async def test_create_spot_bid_limit_order(http_client_authenticated):
    instrument = "test-ticker"

    await REDIS_CLIENT.set(instrument, 100.0)

    body = {
        "order_type": OrderType.LIMIT,
        "quantity": 10,
        "instrument": instrument,
        "side": Side.BID,
        "limit_price": 100.0,
    }

    rsp = await http_client_authenticated.post("/order/spot", json=body)
    data = rsp.json()

    assert rsp.status_code == 201, vars(rsp)
    assert len(data) == 1
    assert "order_id" in data

    async with get_db_sess_async() as sess:
        orders = await sess.execute(
            select(Orders).where(Orders.order_id == data["order_id"])
        )
        orders = orders.scalars().all()

        escrow_balance = await sess.execute(
            select(Escrows.balance).where(Escrows.order_id == data["order_id"])
        )
        escrow_balance = escrow_balance.scalar()
        
        user_balance = await sess.execute(
            select(Users.balance).where(
                Users.user_id
                == select(Orders.user_id)
                .where(Orders.order_id == data["order_id"])
                .scalar_subquery()
            )
        )
        user_balance = user_balance.scalar()

    assert len(orders) == 1
    order = orders[0]
    assert order.instrument == body["instrument"]
    assert order.quantity == body["quantity"]
    assert order.side == body["side"]
    assert order.order_type == body["order_type"]
    assert order.limit_price == body["limit_price"]
    assert escrow_balance == 1000.0
    assert user_balance == get_default_balance() - 1000.0


@pytest.mark.asyncio(loop_scope="module")
async def test_create_spot_bid_order_insufficient_balance(http_client_authenticated):
    body = {
        "order_type": OrderType.LIMIT,
        "quantity": 1000,
        "instrument": "instrument",
        "side": Side.BID,
        "limit_price": 100.0,
    }

    rsp = await http_client_authenticated.post("/order/spot", json=body)

    assert rsp.status_code == 400
    assert "error" in rsp.json()


@pytest.mark.asyncio(loop_scope="module")
async def test_create_spot_ask_limit_order(http_client_authenticated):
    body = {
        "order_type": OrderType.LIMIT,
        "quantity": 10,
        "instrument": "BTC",
        "side": Side.ASK,
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

    assert rsp.status_code == 201, data
    assert "order_id" in data, data


@pytest.mark.asyncio(loop_scope="module")
async def test_create_spot_ask_insufficient_asset_balance(
    http_client_authenticated,
) -> None:
    body = {
        "order_type": OrderType.LIMIT,
        "quantity": 10,
        "instrument": "BTC",
        "side": Side.ASK,
        "limit_price": 100.0,
    }

    rsp = await http_client_authenticated.post("/order/spot", json=body)
    data = rsp.json()

    assert rsp.status_code == 400
    assert "error" in data


@pytest.mark.asyncio(loop_scope="module")
async def test_create_order_non_existent_instrument(http_client_authenticated):
    body = {
        "order_type": OrderType.LIMIT,
        "quantity": 10,
        "instrument": "instrument",
        "side": Side.BID,
        "limit_price": 100.0,
    }

    rsp = await http_client_authenticated.post("/order/spot", json=body)
    data = rsp.json()

    assert rsp.status_code == 400
    assert "error" in data
