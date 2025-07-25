import asyncio
import pytest
import pytest_asyncio
from sqlalchemy import select

from config import REDIS_CLIENT
from db_models import Escrows, OrderEvents, Orders, Users, get_default_user_balance
from engine.typing import EventType
from enums import OrderStatus
from tests.utils import get_db_sess


@pytest.mark.asyncio(loop_scope="module")
async def test_place_order(futures_engine, http_client_authenticated):
    await REDIS_CLIENT.set("TEST-BTC-USD-FUTURES", 100.0)

    body = {
        "instrument": "TEST-BTC-USD-FUTURES",
        "side": "bid",
        "order_type": "limit",
        "quantity": 10,
        "limit_price": 100.0,
    }

    rsp = await http_client_authenticated.post("/order/futures", json=body)
    limit_bid_order_id = rsp.json()["order_id"]

    body = {
        "instrument": "TEST-BTC-USD-FUTURES",
        "side": "ask",
        "order_type": "market",
        "quantity": 10,
    }
    rsp = await http_client_authenticated.post("/order/futures", json=body)
    counter_ask_order_id = rsp.json()["order_id"]

    # Checking escrow balance
    with get_db_sess() as sess:
        bid_escrow = sess.execute(
            select(Escrows.balance).where(Escrows.order_id == limit_bid_order_id)
        ).scalar()
        ask_escrow = sess.execute(
            select(Escrows.balance).where(Escrows.order_id == counter_ask_order_id)
        ).scalar()

        user_balance = sess.execute(
            select(Users.balance).where(
                Users.user_id
                == select(Orders.user_id)
                .where(Orders.order_id == limit_bid_order_id)
                .scalar_subquery()
            )
        ).scalar()

        bid_events = (
            sess.execute(
                select(OrderEvents).where(OrderEvents.order_id == limit_bid_order_id)
            )
            .scalars()
            .all()
        )
        ask_events = (
            sess.execute(
                select(OrderEvents).where(OrderEvents.order_id == counter_ask_order_id)
            )
            .scalars()
            .all()
        )

    assert bid_escrow == 1000.0
    assert ask_escrow == 1000.0

    assert user_balance == get_default_user_balance() - 2000.0

    assert len(bid_events) == 3
    assert len(ask_events) == 2

    assert bid_events[0].event_type == EventType.BID_SUBMITTED
    assert bid_events[1].event_type == EventType.ORDER_NEW
    assert bid_events[1].quantity == 10
    assert bid_events[1].balance == get_default_user_balance() - 1000.0
    assert bid_events[2].event_type == EventType.ORDER_FILLED
    assert bid_events[2].quantity == 10
    assert bid_events[2].asset_balance == 10
    assert bid_events[2].balance == get_default_user_balance() - 2000.0

    assert ask_events[0].event_type == EventType.ASK_SUBMITTED
    assert ask_events[1].event_type == EventType.ORDER_FILLED
    assert ask_events[1].quantity == 10
    assert ask_events[1].asset_balance == 10
    assert ask_events[1].balance == get_default_user_balance() - 2000.0


@pytest.mark.asyncio(loop_scope="module")
async def test_modify_order(
    futures_engine, http_client_authenticated, persisted_futures_order_id
):
    await REDIS_CLIENT.set("TEST-BTC-USD-FUTURES", 100.0)
    rsp = await http_client_authenticated.patch(
        f"/order/modify/{persisted_futures_order_id}", json={"limit_price": 95.0}
    )

    with get_db_sess() as sess:
        escrow = sess.execute(
            select(Escrows.balance).where(
                Escrows.order_id == persisted_futures_order_id
            )
        ).scalar()

        user_balance = sess.execute(
            select(Users.balance).where(
                Users.user_id
                == select(Orders.user_id)
                .where(Orders.order_id == persisted_futures_order_id)
                .scalar_subquery()
            )
        ).scalar()

        events = (
            sess.execute(
                select(OrderEvents).where(
                    OrderEvents.order_id == persisted_futures_order_id
                )
            )
            .scalars()
            .all()
        )

        order = sess.execute(
            select(Orders).where(Orders.order_id == persisted_futures_order_id)
        ).scalar()

    assert escrow == 900.0
    assert user_balance == get_default_user_balance() - 900.0
    assert len(events) == 3

    assert events[0].event_type == EventType.BID_SUBMITTED
    assert events[1].event_type == EventType.ORDER_NEW
    assert events[2].event_type == EventType.ORDER_MODIFIED
    assert events[2].limit_price == 95.0
    assert events[2].take_profit == 110.0
    assert events[2].stop_loss == 80.0

    assert order.limit_price == 95.0


@pytest.mark.asyncio(loop_scope="module")
async def test_fully_cancel_order(
    futures_engine, http_client_authenticated, persisted_futures_order_id
):
    await http_client_authenticated.request(
        "DELETE",
        f"/order/cancel/{persisted_futures_order_id}",
        json={"quantity": "ALL"},
    )

    await asyncio.sleep(1)

    with get_db_sess() as sess:
        user_balance = sess.execute(
            select(Users.balance).where(
                Users.user_id
                == select(Orders.user_id)
                .where(Orders.order_id == persisted_futures_order_id)
                .scalar_subquery()
            )
        ).scalar()

        events = (
            sess.execute(
                select(OrderEvents).where(
                    OrderEvents.order_id == persisted_futures_order_id
                )
            )
            .scalars()
            .all()
        )

        escrow_balance = sess.execute(
            select(Escrows.balance).where(
                Escrows.order_id == persisted_futures_order_id
            )
        ).scalar()

        order = sess.execute(
            select(Orders).where(Orders.order_id == persisted_futures_order_id)
        ).scalar()

    assert user_balance == get_default_user_balance()
    assert escrow_balance == 0

    assert len(events) == 3

    assert events[0].event_type == EventType.BID_SUBMITTED
    assert events[1].event_type == EventType.ORDER_NEW
    assert events[2].event_type == EventType.ORDER_CANCELLED
    assert events[2].quantity == 10
    assert events[2].asset_balance == 0
    assert events[2].balance == get_default_user_balance()

    assert order.status == OrderStatus.CANCELLED
    assert order.standing_quantity == 0


@pytest.mark.asyncio(loop_scope="module")
async def test_close_order(
    futures_engine, http_client_authenticated, persisted_futures_order_id
):
    await REDIS_CLIENT.set("TEST-BTC-USD-FUTURES", 90.0)

    counter_order = {
        "instrument": "TEST-BTC-USD-FUTURES",
        "side": "ask",
        "order_type": "market",
        "quantity": 5,
    }
    await http_client_authenticated.post("/order/futures", json=counter_order)

    await http_client_authenticated.request(
        "DELETE",
        f"/order/close/{persisted_futures_order_id}",
        json={"quantity": "ALL"},
    )

    await asyncio.sleep(1)

    with get_db_sess() as sess:
        user_balance = sess.execute(
            select(Users.balance).where(
                Users.user_id
                == select(Orders.user_id)
                .where(Orders.order_id == persisted_futures_order_id)
                .scalar_subquery()
            )
        ).scalar()

        events = (
            sess.execute(
                select(OrderEvents).where(
                    OrderEvents.order_id == persisted_futures_order_id
                )
            )
            .scalars()
            .all()
        )

        escrow_balance = sess.execute(
            select(Escrows.balance).where(
                Escrows.order_id == persisted_futures_order_id
            )
        ).scalar()

        order = sess.execute(
            select(Orders).where(Orders.order_id == persisted_futures_order_id)
        ).scalar()

    assert user_balance == get_default_user_balance()
    assert escrow_balance == 0
