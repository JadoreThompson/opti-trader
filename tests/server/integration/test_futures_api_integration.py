import asyncio
import pytest

from sqlalchemy import select

from config import REDIS_CLIENT
from db_models import Escrows, OrderEvents, Orders, Users, get_default_user_balance
from engine.typing import EventType
from enums import OrderStatus
from tests.utils import get_db_sess


@pytest.mark.asyncio(scope="session")
async def test_place_order(futures_engine, http_client_authenticated):
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
    await REDIS_CLIENT.set("TEST-BTC-USD-FUTURES", 100.0)
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


@pytest.mark.asyncio(scope="session")
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


@pytest.mark.asyncio(scope="session")
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


@pytest.mark.asyncio(scope="session")
async def test_close_order_no_profit(
    futures_engine, http_client_authenticated, persisted_futures_order_id
):
    await REDIS_CLIENT.set("TEST-BTC-USD-FUTURES", 90.0)
    await http_client_authenticated.patch(
        f"/order/modify/{persisted_futures_order_id}",
        json={"stop_loss": None, "take_profit": None},
    )

    counter_order = {
        "instrument": "TEST-BTC-USD-FUTURES",
        "side": "ask",
        "order_type": "market",
        "quantity": 5,
    }
    await http_client_authenticated.post("/order/futures", json=counter_order)

    resting_bid = {
        "instrument": "TEST-BTC-USD-FUTURES",
        "side": "bid",
        "order_type": "limit",
        "limit_price": 90.0,
        "quantity": 10,
    }
    await http_client_authenticated.post("/order/futures", json=resting_bid)

    await asyncio.sleep(1)

    await http_client_authenticated.request(
        "DELETE",
        f"/order/close/{persisted_futures_order_id}",
        json={"quantity": "ALL"},
    )

    await asyncio.sleep(3)

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

    # Original escrow for the limit bid as 450.0.
    # The market order filled 5 at 90.0 for 0.0 additional pnl.
    # Other orders occupy the escrow. Making it 2250.0 - 450.0
    assert user_balance == get_default_user_balance() - 1800.0
    # Original escrow was 900.0, half quantity is closed leaving 450.0
    assert escrow_balance == 450.0
    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert order.standing_quantity == 5
    assert len(events) == 5, [e.event_type for e in events]


@pytest.mark.asyncio(scope="session")
async def test_close_order_profit(
    futures_engine, http_client_authenticated, persisted_futures_order_id
):
    await http_client_authenticated.patch(
        f"/order/modify/{persisted_futures_order_id}",
        json={"stop_loss": None, "take_profit": None},
    )

    await REDIS_CLIENT.set("TEST-BTC-USD-FUTURES", 90.0)
    counter_order = {
        "instrument": "TEST-BTC-USD-FUTURES",
        "side": "ask",
        "order_type": "market",
        "quantity": 5,
    }
    await http_client_authenticated.post("/order/futures", json=counter_order)

    resting_bid = {
        "instrument": "TEST-BTC-USD-FUTURES",
        "side": "bid",
        "order_type": "limit",
        "limit_price": 100.0,
        "quantity": 10,
    }
    await http_client_authenticated.post("/order/futures", json=resting_bid)

    await asyncio.sleep(1)

    await http_client_authenticated.request(
        "DELETE",
        f"/order/close/{persisted_futures_order_id}",
        json={"quantity": "ALL"},
    )

    await asyncio.sleep(3)

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

    # Original escrow for the limit bid as 450.0.
    # The market order filled 5 at 100.0 for 100.0 additional pnl.
    # Other orders occupy the escrow. Making it 2350.0 - 500.0
    assert user_balance == get_default_user_balance() - 1850.0
    # Original escrow was 900.0, half quantity is closed leaving 450.0
    assert escrow_balance == 450.0, f"Balance {escrow_balance}"
    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert order.standing_quantity == 5
    assert len(events) == 5


@pytest.mark.asyncio(scope="session")
async def test_close_order_loss(
    futures_engine, http_client_authenticated, persisted_futures_order_id
):
    await http_client_authenticated.patch(
        f"/order/modify/{persisted_futures_order_id}",
        json={"stop_loss": None, "take_profit": None},
    )

    await REDIS_CLIENT.set("TEST-BTC-USD-FUTURES", 90.0)
    counter_order = {
        "instrument": "TEST-BTC-USD-FUTURES",
        "side": "ask",
        "order_type": "market",
        "quantity": 10,
    }
    await http_client_authenticated.post("/order/futures", json=counter_order)

    resting_bid = {
        "instrument": "TEST-BTC-USD-FUTURES",
        "side": "bid",
        "order_type": "limit",
        "limit_price": 80.0,
        "quantity": 10,
    }
    await http_client_authenticated.post("/order/futures", json=resting_bid)

    await asyncio.sleep(1)

    await http_client_authenticated.request(
        "DELETE",
        f"/order/close/{persisted_futures_order_id}",
        json={"quantity": "ALL"},
    )

    await asyncio.sleep(3)

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

    # Total escrow on table for al lordes is 2600.0.
    # The original escrow for the first limit bid was 900.0
    # The limit bid was closed at 80.0, 10.0 less than
    # the original price, resulting in a 100.0 loss.
    # The user is then owed 800.0 which is 100.0 less than the original
    # 900.0 which was the escrow. Resulting in 1800.0 escrow still
    # on the table.
    assert user_balance == get_default_user_balance() - 1800.0
    # Original escrow was 900.0, full quantity is closed leaving 0.0
    assert escrow_balance == 0.0, f"Balance {escrow_balance}"
    assert order.status == OrderStatus.CLOSED
    assert order.standing_quantity == 0
    assert len(events) == 5
