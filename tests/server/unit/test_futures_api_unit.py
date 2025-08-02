import asyncio
import pytest

from faker import Faker
from sqlalchemy import insert, update
from uuid import uuid4

from config import REDIS_CLIENT
from db_models import Orders, OrderStatus, Users
from enums import OrderType, Side
from tests.utils import get_db_sess


@pytest.mark.asyncio(scope="session")
async def test_create_market_order(http_client_authenticated, instrument):
    market_bid = {
        "side": Side.BID,
        "order_type": OrderType.MARKET,
        "quantity": 10,
        "instrument": instrument,
    }

    rsp = await http_client_authenticated.post("/order/futures", json=market_bid)
    assert rsp.status_code == 201
    assert (rsp.json() or {}).get("order_id") is not None


@pytest.mark.asyncio(scope="session")
async def test_create_market_order_limit_price_error(
    http_client_authenticated, instrument
):
    market_bid = {
        "side": Side.BID,
        "order_type": OrderType.MARKET,
        "quantity": 10,
        "instrument": instrument,
        "limit_price": 100.0,
    }

    rsp = await http_client_authenticated.post("/order/futures", json=market_bid)
    assert rsp.status_code == 422
    assert (rsp.json() or {}).get("order_id") is None


@pytest.mark.asyncio(scope="session")
async def test_create_limit_order(http_client_authenticated, instrument):
    limit_bid = {
        "side": Side.BID,
        "order_type": OrderType.LIMIT,
        "limit_price": 100.0,
        "quantity": 10,
        "instrument": instrument,
    }

    rsp = await http_client_authenticated.post("/order/futures", json=limit_bid)
    assert rsp.status_code == 201
    assert (rsp.json() or {}).get("order_id") is not None


@pytest.mark.asyncio(scope="session")
async def test_create_limit_order_no_limit_price_error(
    http_client_authenticated, instrument
):
    limit_bid = {
        "side": Side.BID,
        "order_type": OrderType.LIMIT,
        "quantity": 10,
        "instrument": instrument,
    }

    rsp = await http_client_authenticated.post("/order/futures", json=limit_bid)
    assert rsp.status_code == 422
    assert (rsp.json() or {}).get("order_id") is None


@pytest.mark.asyncio(scope="session")
async def test_create_order_no_side_error(http_client_authenticated, instrument):
    limit_bid = {
        "order_type": OrderType.LIMIT,
        "quantity": 10,
        "instrument": instrument,
    }

    rsp = await http_client_authenticated.post("/order/futures", json=limit_bid)
    assert rsp.status_code == 422
    assert (rsp.json() or {}).get("order_id") is None


@pytest.mark.asyncio(scope="session")
async def test_create_order_no_order_type_error(http_client_authenticated, instrument):
    order = {
        "side": Side.BID,
        "quantity": 10,
        "instrument": instrument,
    }

    rsp = await http_client_authenticated.post("/order/futures", json=order)
    assert rsp.status_code == 422
    assert (rsp.json() or {}).get("order_id") is None


@pytest.mark.asyncio(scope="session")
async def test_create_order_insufficient_balance(http_client_authenticated, instrument):
    order = {
        "side": Side.BID,
        "order_type": OrderType.LIMIT,
        "quantity": 1000,
        "instrument": instrument,
        "limit_price": 100.0,
    }

    rsp = await http_client_authenticated.post("/order/futures", json=order)
    assert rsp.status_code == 400
    assert (rsp.json() or {}).get("order_id") is None


############### MODIFY ORDER TESTS ###############


@pytest.mark.asyncio(scope="session")
async def test_modify_order_success(
    http_client_authenticated, persisted_futures_order_id
):
    """Happy Path: Successfully modify all valid fields of a futures order."""
    modify_payload = {
        "limit_price": 95.0,
        "take_profit": 120.0,
        "stop_loss": 85.0,
    }
    rsp = await http_client_authenticated.patch(
        f"/order/{persisted_futures_order_id}/modify", json=modify_payload
    )
    assert rsp.status_code == 201


@pytest.mark.asyncio(scope="session")
async def test_modify_order_not_found(http_client_authenticated):
    """Error Path: Attempt to modify an order that does not exist."""
    fake_order_id = uuid4()
    modify_payload = {"limit_price": 100.0}
    rsp = await http_client_authenticated.patch(
        f"/order/{fake_order_id}/modify", json=modify_payload
    )
    assert rsp.status_code == 400
    assert "Order doesn't exist" in rsp.json()["error"]


@pytest.mark.asyncio(scope="session")
async def test_modify_order_already_closed(
    http_client_authenticated, persisted_futures_order_id
):
    """Error Path: Attempt to modify an order that is already closed."""
    with get_db_sess() as sess:
        sess.execute(
            update(Orders)
            .values(status=OrderStatus.CLOSED.value)
            .where(Orders.order_id == persisted_futures_order_id)
        )
        sess.commit()

    modify_payload = {"limit_price": 100.0}
    rsp = await http_client_authenticated.patch(
        f"/order/{persisted_futures_order_id}/modify", json=modify_payload
    )
    assert rsp.status_code == 400
    assert "Cannot modify closed order" in rsp.json()["error"]


@pytest.mark.asyncio(scope="session")
async def test_modify_order_wrong_user(
    http_client_authenticated, persisted_futures_order_id
):
    """Error Path: Attempt to modify an order belonging to another user."""
    with get_db_sess() as sess:
        wrong_user_id = sess.execute(
            insert(Users)
            .values(username="jake", password="password")
            .returning(Users.user_id)
        ).scalar()

        sess.execute(
            update(Orders)
            .values(user_id=wrong_user_id)
            .where(Orders.order_id == persisted_futures_order_id)
        )

        sess.execute(
            update(Orders)
            .values(status=OrderStatus.PENDING.value)
            .where(Orders.order_id == persisted_futures_order_id)
        )
        sess.commit()

    modify_payload = {"limit_price": 100.0}
    rsp = await http_client_authenticated.patch(
        f"/order/{persisted_futures_order_id}/modify", json=modify_payload
    )
    assert rsp.status_code == 400
    assert "Order doesn't exist" in rsp.json()["error"]


@pytest.mark.asyncio(scope="session")
async def test_modify_order_invalid_payload(
    http_client_authenticated, persisted_futures_order_id
):
    """Error Path: Send a payload with an incorrect data type."""
    modify_payload = {"limit_price": "not-a-float"}
    rsp = await http_client_authenticated.patch(
        f"/order/{persisted_futures_order_id}/modify", json=modify_payload
    )
    assert rsp.status_code == 422


@pytest.mark.asyncio(scope="session")
async def test_modify_order_negative_value(
    http_client_authenticated, persisted_futures_order_id
):
    """Error Path: Send a payload with an incorrect data type."""
    modify_payload = {"limit_price": -1}
    rsp = await http_client_authenticated.patch(
        f"/order/{persisted_futures_order_id}/modify", json=modify_payload
    )
    assert rsp.status_code == 422


@pytest.mark.asyncio(scope="session")
async def test_modify_order_unauthenticated(http_client, persisted_futures_order_id):
    """Error Path: Attempt to modify an order without being authenticated."""
    modify_payload = {"limit_price": 100.0}
    rsp = await http_client.patch(
        f"/order/{persisted_futures_order_id}/modify", json=modify_payload
    )
    assert rsp.status_code == 403


@pytest.mark.asyncio(scope="session")
async def test_modify_order_null_limit_price_fails(
    http_client_authenticated, persisted_futures_order_id
):
    """
    Error Path: Test the specific endpoint constraint that rejects modifications
    if limit_price is null.
    """
    modify_payload = {"limit_price": None}
    rsp = await http_client_authenticated.patch(
        f"/order/{persisted_futures_order_id}/modify", json=modify_payload
    )
    assert rsp.status_code == 400


############### CANCEL ORDER TESTS ###############


@pytest.mark.asyncio(scope="session")
async def test_cancel_order_partial_success(
    http_client_authenticated, persisted_futures_order_id
):
    """Happy Path: Successfully cancel a part of an order's standing quantity."""
    cancel_payload = {"quantity": 5}
    rsp = await http_client_authenticated.request(
        "DELETE", url=f"/order/cancel/{persisted_futures_order_id}", json=cancel_payload
    )
    assert rsp.status_code == 201


@pytest.mark.asyncio(scope="session")
async def test_cancel_order_full_success(
    http_client_authenticated, persisted_futures_order_id
):
    """Happy Path: Successfully cancel the full standing quantity of an order."""
    cancel_payload = {"quantity": 10}
    rsp = await http_client_authenticated.request(
        "DELETE", url=f"/order/cancel/{persisted_futures_order_id}", json=cancel_payload
    )
    assert rsp.status_code == 201


@pytest.mark.asyncio(scope="session")
async def test_cancel_order_not_found(http_client_authenticated):
    """Error Path: Attempt to cancel an order that does not exist."""
    fake_order_id = uuid4()
    cancel_payload = {"quantity": 1}
    rsp = await http_client_authenticated.request(
        "DELETE", url=f"/order/cancel/{fake_order_id}", json=cancel_payload
    )
    assert rsp.status_code == 400
    assert "Order doesn't exist" in rsp.json()["error"]


@pytest.mark.asyncio(scope="session")
async def test_cancel_order_wrong_user(
    http_client_authenticated, persisted_futures_order_id
):
    """Error Path: Attempt to cancel an order belonging to another user."""
    with get_db_sess() as sess:
        wrong_user_id = sess.execute(
            insert(Users)
            .values(username=Faker().user_name(), password="password")
            .returning(Users.user_id)
        ).scalar()
        sess.execute(
            update(Orders)
            .values(user_id=wrong_user_id)
            .where(Orders.order_id == persisted_futures_order_id)
        )
        sess.commit()
    cancel_payload = {"quantity": 5}
    rsp = await http_client_authenticated.request(
        "DELETE", url=f"/order/cancel/{persisted_futures_order_id}", json=cancel_payload
    )
    assert rsp.status_code == 400
    assert "Order doesn't exist" in rsp.json()["error"]


@pytest.mark.asyncio(scope="session")
async def test_cancel_order_insufficient_quantity(
    http_client_authenticated, persisted_futures_order_id
):
    """Error Path: Attempt to cancel more than the standing quantity."""
    cancel_payload = {"quantity": 11}
    rsp = await http_client_authenticated.request(
        "DELETE", url=f"/order/cancel/{persisted_futures_order_id}", json=cancel_payload
    )
    assert rsp.status_code == 400
    assert "Insufficient standing quantity" in rsp.json()["error"]


@pytest.mark.asyncio(scope="session")
async def test_cancel_order_invalid_payload(
    http_client_authenticated, persisted_futures_order_id
):
    """Error Path: Send a payload with an incorrect data type for quantity."""
    cancel_payload = {"quantity": "not-an-int"}
    rsp = await http_client_authenticated.request(
        "DELETE", url=f"/order/cancel/{persisted_futures_order_id}", json=cancel_payload
    )
    assert rsp.status_code == 422


@pytest.mark.asyncio(scope="session")
async def test_cancel_order_unauthenticated(http_client, persisted_futures_order_id):
    """Error Path: Attempt to cancel an order without being authenticated."""
    cancel_payload = {"quantity": 5}
    rsp = await http_client.request(
        "DELETE", url=f"/order/cancel/{persisted_futures_order_id}", json=cancel_payload
    )
    assert rsp.status_code == 403


############### CLOSE ORDER TESTS ###############


@pytest.mark.asyncio(scope="session")
async def test_close_order(
    futures_engine,
    http_client_authenticated,
    persisted_futures_order_id,
):
    """Successfully close a futures order."""

    await REDIS_CLIENT.set("TEST-BTC-USD-FUTURES", 90.0)

    counter_order = {
        "side": Side.ASK,
        "order_type": OrderType.MARKET,
        "quantity": 10,
        "instrument": "TEST-BTC-USD-FUTURES",
    }

    await http_client_authenticated.post("/order/futures", json=counter_order)
    await asyncio.sleep(1)  # Allow time for the order to be processed

    rsp = await http_client_authenticated.request(
        "DELETE",
        url=f"/order/{persisted_futures_order_id}/close",
        json={"quantity": "ALL"},
    )

    assert rsp.status_code == 201


@pytest.mark.asyncio(scope="session")
async def test_close_order(
    futures_engine,
    http_client_authenticated,
    persisted_futures_order_id,
):
    """Successfully close a futures order."""

    await REDIS_CLIENT.set("TEST-BTC-USD-FUTURES", 90.0)

    counter_order = {
        "side": Side.ASK,
        "order_type": OrderType.MARKET,
        "quantity": 10,
        "instrument": "TEST-BTC-USD-FUTURES",
    }

    await http_client_authenticated.post("/order/futures", json=counter_order)
    await asyncio.sleep(1)  # Allow time for the order to be processed

    rsp = await http_client_authenticated.request(
        "DELETE",
        url=f"/order/{persisted_futures_order_id}/close",
        json={"quantity": "ALL"},
    )

    assert rsp.status_code == 201


@pytest.mark.asyncio(scope="session")
async def test_close_order_non_existent(http_client_authenticated):
    """Error Path: Attempt to close an order that does not exist."""
    fake_order_id = uuid4()
    rsp = await http_client_authenticated.request(
        "DELETE", url=f"/order/{fake_order_id}/close", json={"quantity": "ALL"}
    )
    assert rsp.status_code == 400
    assert "Order doesn't exist" in rsp.json()["error"]


@pytest.mark.asyncio(scope="session")
async def test_close_order_sub_zero(
    http_client_authenticated, persisted_futures_order_id
):
    """Error Path: Attempt to close an order that does not exist."""
    rsp = await http_client_authenticated.request(
        "DELETE",
        url=f"/order/{persisted_futures_order_id}/close",
        json={"quantity": -1},
    )
    assert rsp.status_code == 422


@pytest.mark.asyncio(scope="session")
async def test_close_order_invalid_string(
    http_client_authenticated, persisted_futures_order_id
):
    """Error Path: Attempt to close an order that does not exist."""
    rsp = await http_client_authenticated.request(
        "DELETE",
        url=f"/order/{persisted_futures_order_id}/close",
        json={"quantity": "NONE"},
    )
    assert rsp.status_code == 422
