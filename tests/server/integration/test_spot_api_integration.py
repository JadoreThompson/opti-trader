import asyncio
import pytest

from sqlalchemy import func, insert, select, update
from config import REDIS_CLIENT
from db_models import OrderEvents, Orders, Users, get_default_balance
from engine import SpotEngine
from engine.balance_manager import BalanceManager
from engine.orderbook.orderbook import OrderBook
from engine.typing import EventType
from enums import MarketType, OrderStatus, OrderType, Side
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
    """
    Scenario: A user places a spot market bid order. The system should
        successfully accept the order and log the 'BID_SUBMITTED' and
        'ORDER_PLACED' events in the database.
    """
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

    assert len(events) == 2
    assert events[0].event_type == EventType.BID_SUBMITTED
    assert events[1].event_type == EventType.ORDER_PLACED
    assert str(events[1].order_id) == data["order_id"]


@pytest.mark.asyncio(loop_scope="module")
async def test_spot_bid_limit_order_integration(
    http_client_authenticated, patched_log, engine
):
    """
    Scenario: A user places a spot limit bid order. The system should
        successfully accept the order and log the 'BID_SUBMITTED' and
        'ORDER_PLACED' events.
    """
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

    assert len(events) == 2, [e.event_type for e in events]
    assert events[0].event_type == EventType.BID_SUBMITTED
    assert events[1].event_type == EventType.ORDER_PLACED
    assert str(events[1].order_id) == data["order_id"]


@pytest.mark.asyncio(loop_scope="module")
async def test_spot_ask_limit_order_integration(
    http_client_authenticated, patched_log, engine
):
    """
    Scenario: After simulating a previous fill to establish an asset
        balance, a user places a spot limit ask order. The system should
        successfully accept the new order and log an 'ORDER_PLACED' event.
    """
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
        # Simulating previous fill
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


@pytest.mark.asyncio(loop_scope="module")
async def test_modify_spot_limit_order_integration(
    http_client_authenticated, patched_log, engine
):
    """
    Scenario: A user places a spot limit bid order and then successfully
        modifies its limit price. The system should log an
        'ORDER_MODIFIED' event and update the order's price in the
        database.
    """
    initial_limit_price = 100.0
    body = {
        "order_type": OrderType.LIMIT,
        "quantity": 10,
        "instrument": "BTC",
        "side": Side.BID,
        "limit_price": initial_limit_price,
    }

    rsp = await http_client_authenticated.post("/order/spot", json=body)
    assert rsp.status_code == 201
    order_id = rsp.json()["order_id"]

    new_limit_price = 80.0
    body = {"limit_price": new_limit_price}

    rsp = await http_client_authenticated.patch(f"/order/modify/{order_id}", json=body)
    assert rsp.status_code == 201

    async with get_db_sess_async() as sess:
        res = await sess.execute(
            select(OrderEvents).where(
                OrderEvents.order_id == order_id,
                OrderEvents.event_type == EventType.ORDER_MODIFIED,
            )
        )
        modified_event = res.scalar_one_or_none()

        res = await sess.execute(select(Orders).where(Orders.order_id == order_id))
        updated_order = res.scalar_one_or_none()

    assert modified_event is not None, "ORDER_MODIFIED event was not logged"
    assert modified_event.limit_price == new_limit_price

    assert updated_order is not None, "Order record not found after modification"
    assert updated_order.limit_price == new_limit_price


@pytest.mark.asyncio(loop_scope="module")
async def test_modify_spot_ask_limit_order_integration(
    http_client_authenticated, patched_log, engine
):
    """
    Scenario: After acquiring an asset from a previous fill, a user
        places a spot limit ask order and then successfully modifies its
        limit price. The system should log the modification event and
        update the order record.
    """
    instrument = "BTC"
    rsp = await http_client_authenticated.get("/auth/me-id")
    user_id = rsp.json()["user_id"]

    async with get_db_sess_async() as sess:
        # Simulating previous fill
        res = await sess.execute(
            insert(Orders)
            .values(
                user_id=user_id,
                order_type=OrderType.MARKET,
                market_type=MarketType.SPOT,
                instrument=instrument,
                side=Side.BID,
                standing_quantity=0,
                open_quantity=20,
                quantity=20,
            )
            .returning(Orders.order_id)
        )
        filled_order_id = res.scalar()
        await sess.execute(
            insert(OrderEvents).values(
                event_type=EventType.ORDER_FILLED,
                user_id=user_id,
                order_id=filled_order_id,
                asset_balance=20,
                balance=8000.0,
            )
        )
        await sess.commit()

    # Simulating previous fill
    _, balance_manager = engine._orderbooks.setdefault(
        instrument, (OrderBook(), BalanceManager())
    )
    balance_manager._users[user_id] = 100

    initial_limit_price = 200.0
    create_body = {
        "order_type": OrderType.LIMIT,
        "quantity": 10,
        "instrument": instrument,
        "side": Side.ASK,
        "limit_price": initial_limit_price,
    }
    create_rsp = await http_client_authenticated.post("/order/spot", json=create_body)
    assert create_rsp.status_code == 201
    order_id = create_rsp.json()["order_id"]

    new_limit_price = 210.0
    modify_body = {"limit_price": new_limit_price}
    modify_rsp = await http_client_authenticated.patch(
        f"/order/modify/{order_id}", json=modify_body
    )
    assert modify_rsp.status_code == 201

    async with get_db_sess_async() as sess:
        modified_event = await sess.scalar(
            select(OrderEvents).where(
                OrderEvents.order_id == order_id,
                OrderEvents.event_type == EventType.ORDER_MODIFIED,
            )
        )
        updated_order = await sess.scalar(
            select(Orders).where(Orders.order_id == order_id)
        )

    assert modified_event is not None
    assert updated_order is not None
    assert updated_order.limit_price == new_limit_price


@pytest.mark.asyncio(loop_scope="module")
async def test_modify_spot_bid_order_rejected_integration(
    http_client_authenticated, patched_log, engine
):
    """
    Scenario: A user places a limit bid and then attempts to modify its
        price to one that violates a market rule (e.g., price is too
        high). The modification should be rejected by the engine, an
        'ORDER_REJECTED' event should be logged, and the original order
        should remain unchanged.
    """
    instrument = "**"
    market_price = 100.0
    await REDIS_CLIENT.set(instrument, market_price)

    initial_limit_price = 90.0
    body = {
        "order_type": OrderType.LIMIT,
        "quantity": 10,
        "instrument": instrument,
        "side": Side.BID,
        "limit_price": initial_limit_price,
    }
    rsp = await http_client_authenticated.post("/order/spot", json=body)
    assert rsp.status_code == 201
    order_id = rsp.json()["order_id"]

    await asyncio.sleep(0.1)

    rejected_limit_price = 110.0
    body = {"limit_price": rejected_limit_price}
    rsp = await http_client_authenticated.patch(f"/order/modify/{order_id}", json=body)
    assert rsp.status_code == 201

    async with get_db_sess_async() as sess:
        rejected_event = await sess.scalar(
            select(OrderEvents).where(
                OrderEvents.order_id == order_id,
                OrderEvents.event_type == EventType.ORDER_REJECTED,
            )
        )
        final_order = await sess.scalar(
            select(Orders).where(Orders.order_id == order_id)
        )

    assert rejected_event is not None, "ORDER_REJECTED event was not logged"
    assert (
        final_order.limit_price == initial_limit_price
    ), "Order price should not have been modified"


@pytest.mark.asyncio(loop_scope="module")
async def test_modify_spot_ask_order_rejected_integration(
    http_client_authenticated, patched_log, engine
):
    """
    Scenario: A user places a limit ask and then attempts to modify its
        price to one that violates a market rule (e.g., price is too
        low). The modification should be rejected, an 'ORDER_REJECTED'
        event logged, and the original order remains unchanged.
    """
    instrument = "BTC"
    market_price = 100.0
    await REDIS_CLIENT.set(instrument, market_price)

    rsp = await http_client_authenticated.get("/auth/me-id")
    user_id = rsp.json()["user_id"]
    async with get_db_sess_async() as sess:
        # Simulating previous fill
        res = await sess.execute(
            insert(Orders)
            .values(
                user_id=user_id,
                order_type=OrderType.MARKET,
                market_type=MarketType.SPOT,
                instrument=instrument,
                side=Side.BID,
                standing_quantity=0,
                open_quantity=20,
                quantity=20,
            )
            .returning(Orders.order_id)
        )
        order_id = res.scalar()
        await sess.execute(
            insert(OrderEvents).values(
                event_type=EventType.ORDER_FILLED,
                user_id=user_id,
                order_id=order_id,
                asset_balance=20,
                balance=8000.0,  # random value < 10_000
            )
        )
        await sess.commit()

    _, balance_manager = engine._orderbooks.setdefault(
        instrument, (OrderBook(), BalanceManager())
    )
    balance_manager._users[user_id] = 100
    initial_limit_price = 110.0
    body = {
        "order_type": OrderType.LIMIT,
        "quantity": 10,
        "instrument": instrument,
        "side": Side.ASK,
        "limit_price": initial_limit_price,
    }
    rsp = await http_client_authenticated.post("/order/spot", json=body)
    assert rsp.status_code == 201
    order_id = rsp.json()["order_id"]

    rejected_limit_price = 90.0
    modify_body = {"limit_price": rejected_limit_price}
    modify_rsp = await http_client_authenticated.patch(
        f"/order/modify/{order_id}", json=modify_body
    )
    assert modify_rsp.status_code == 201

    async with get_db_sess_async() as sess:
        rejected_event = await sess.scalar(
            select(OrderEvents).where(
                OrderEvents.order_id == order_id,
                OrderEvents.event_type == EventType.ORDER_REJECTED,
            )
        )
        final_order = await sess.scalar(
            select(Orders).where(Orders.order_id == order_id)
        )

    assert rejected_event is not None, "ORDER_REJECTED event was not logged"
    assert (
        final_order.limit_price == initial_limit_price
    ), "Order price should not have been modified"


@pytest.mark.asyncio(loop_scope="module")
async def test_cancel_order_integration(
    http_client_authenticated, patched_log, engine, payload_pusher, payload_queue
):
    """
    Scenario: A user places a limit order and then sends a request to
        cancel the entire order. The system should log the
        'ORDER_CANCELLED' event and update the order's status and
        standing quantity accordingly.
    """
    engine._payload_queue = payload_queue

    body = {
        "order_type": OrderType.LIMIT,
        "quantity": 10,
        "instrument": "BTC",
        "side": Side.BID,
        "limit_price": 90.0,
    }
    rsp_create = await http_client_authenticated.post("/order/spot", json=body)
    assert rsp_create.status_code == 201
    order_id = rsp_create.json()["order_id"]

    cancel_body = {"quantity": 10}
    rsp_cancel = await http_client_authenticated.request(
        "DELETE", url=f"/order/cancel/{order_id}", json=cancel_body
    )
    await asyncio.sleep(1)  # Allowing PayloadPusher to commit

    assert rsp_cancel.status_code == 201, rsp_cancel.json()

    async with get_db_sess_async() as sess:
        cancelled_event = await sess.scalar(
            select(OrderEvents).where(
                OrderEvents.order_id == order_id,
                OrderEvents.event_type == EventType.ORDER_CANCELLED,
            )
        )
        cancelled_order = await sess.scalar(
            select(Orders).where(Orders.order_id == order_id)
        )

    assert cancelled_event is not None, "ORDER_CANCELLED event was not logged"
    assert cancelled_order is not None
    assert cancelled_order.status == OrderStatus.CANCELLED
    assert cancelled_order.standing_quantity == 0


@pytest.mark.asyncio(loop_scope="module")
async def test_partial_cancel_order_integration(
    http_client_authenticated, patched_log, engine, payload_pusher, payload_queue
):
    """
    Scenario: A user places a limit order and then sends a request to
        partially cancel it. The system should log the 'ORDER_CANCELLED'
        event for the cancelled portion and update the order's standing
        quantity, while the order remains pending.
    """
    engine._payload_queue = payload_queue
    order_quantity = 10
    cancel_quantity = 4

    body = {
        "order_type": OrderType.LIMIT,
        "quantity": order_quantity,
        "instrument": "BTC",
        "side": Side.BID,
        "limit_price": 91.0,
    }
    rsp_create = await http_client_authenticated.post("/order/spot", json=body)
    assert rsp_create.status_code == 201
    order_id = rsp_create.json()["order_id"]
    await asyncio.sleep(0.1)

    async with get_db_sess_async() as sess:
        await sess.execute(
            update(Orders)
            .where(Orders.order_id == order_id)
            .values(open_quantity=order_quantity)
        )
        await sess.commit()

    cancel_body = {"quantity": cancel_quantity}
    rsp_cancel = await http_client_authenticated.request(
        "DELETE", url=f"/order/cancel/{order_id}", json=cancel_body
    )

    await asyncio.sleep(1)

    assert rsp_cancel.status_code == 201

    async with get_db_sess_async() as sess:
        cancelled_event = await sess.scalar(
            select(OrderEvents).where(
                OrderEvents.order_id == order_id,
                OrderEvents.event_type == EventType.ORDER_CANCELLED,
            )
        )
        updated_order = await sess.scalar(
            select(Orders).where(Orders.order_id == order_id)
        )

    assert cancelled_event is not None
    assert cancelled_event.quantity == cancel_quantity
    assert updated_order is not None
    assert updated_order.status == OrderStatus.PENDING
    assert updated_order.standing_quantity == order_quantity - cancel_quantity


@pytest.mark.asyncio(loop_scope="module")
async def test_cancel_filled_order_is_ignored_integration(
    http_client_authenticated, patched_log, engine, payload_pusher, payload_queue
):
    """
    Scenario: A user places an order that gets fully filled. A subsequent
        attempt to cancel this filled order should be rejected, and the
        order's status should remain 'FILLED' with no cancellation event
        logged.
    """
    engine._payload_queue = payload_queue
    instrument = "DOGE"
    price = 0.1
    quantity = 100
    await REDIS_CLIENT.set(instrument, price)

    rsp_bid = await http_client_authenticated.post(
        "/order/spot",
        json={
            "order_type": OrderType.LIMIT,
            "quantity": quantity,
            "instrument": instrument,
            "side": Side.BID,
            "limit_price": price,
        },
    )
    assert rsp_bid.status_code == 201
    bid_order_id = rsp_bid.json()["order_id"]

    # Pre-requisites for ask order.
    async with get_db_sess_async() as sess:
        res = await sess.execute(
            insert(Users)
            .values(username="test-user-allen", password="password111")
            .returning(Users.user_id)
        )
        user_id = res.scalar()
        res = await sess.execute(
            insert(Orders)
            .values(
                **{
                    "instrument": instrument,
                    "user_id": user_id,
                    "side": Side.ASK,
                    "order_type": OrderType.LIMIT,
                    "quantity": quantity,
                    "market_type": MarketType.SPOT,
                    "standing_quantity": quantity,
                    "limit_price": price,
                    "status": "pending",
                    "open_quantity": 0,
                }
            )
            .returning(Orders)
        )
        ask_order = res.scalar()
        await sess.commit()

    ask_order.user_id = str(ask_order.user_id)
    ask_order.order_id = str(ask_order.order_id)

    _, balance_manager = engine._orderbooks[ask_order.instrument]
    balance_manager.append(ask_order.user_id)
    balance_manager._users[ask_order.user_id] = quantity

    engine.place_order(ask_order.dump())

    await asyncio.sleep(1)  # Giving PayloadPusher some time

    async with get_db_sess_async() as sess:
        filled_order = await sess.scalar(
            select(Orders).where(Orders.order_id == bid_order_id)
        )

    assert filled_order is not None
    assert filled_order.status == OrderStatus.FILLED

    rsp_cancel = await http_client_authenticated.request(
        "DELETE", url=f"/order/cancel/{bid_order_id}", json={"quantity": quantity}
    )
    assert rsp_cancel.status_code == 400
    await asyncio.sleep(1)  # Giving PayloadPusher some time

    async with get_db_sess_async() as sess:
        cancel_event_count = await sess.scalar(
            select(func.count())
            .select_from(OrderEvents)
            .where(
                OrderEvents.order_id == bid_order_id,
                OrderEvents.event_type == EventType.ORDER_CANCELLED,
            )
        )
        final_order = await sess.scalar(
            select(Orders).where(Orders.order_id == bid_order_id)
        )

    assert cancel_event_count == 0
    assert final_order.status == OrderStatus.FILLED
