
import pytest
import uuid
from faker import Faker

from src.enums import OrderType, Side, OrderStatus
from src.engine import CommandType
from src.engine.models import (
    NewSingleOrder,
    NewOCOOrder,
    NewOTOOrder,
    NewOTOCOOrder,
    CancelOrderCommand,
    ModifyOrderCommand,
)
from src.db_models import Orders, Trades, Users
from src.config import PAGE_SIZE


@pytest.mark.asyncio
async def test_create_single_limit_order(async_client, test_instrument, monkeypatch):
    """Tests successful creation of a single LIMIT order."""
    client, mock_queue, _ = async_client

    order_data = {
        "instrument_id": test_instrument.instrument_id,
        "order_type": OrderType.LIMIT.value,
        "side": Side.BID.value,
        "quantity": 10.5,
        "limit_price": 25000.0,
    }

    response = await client.post("/orders/", json=order_data)

    assert response.status_code == 202
    json_response = response.json()
    assert "order_id" in json_response
    assert uuid.UUID(json_response["order_id"])

    mock_queue.put_nowait.assert_called_once()
    cmd = mock_queue.put_nowait.call_args[0][0]
    assert cmd.command_type.value == CommandType.NEW_ORDER.value
    assert type(cmd.data).__name__ == "NewSingleOrder"
    assert cmd.data.instrument_id == test_instrument.instrument_id
    assert cmd.data.order["quantity"] == 10.5
    assert cmd.data.order["limit_price"] == 25000.0


@pytest.mark.asyncio(scope="session")
async def test_create_market_order_with_escrow(
    async_client, async_db_session, test_instrument, order_factory_db
):
    """Tests successful creation of a MARKET order, verifying escrow logic."""
    client, mock_queue, user = async_client

    # A temporary order is needed for the trade record foreign key
    temp_order = order_factory_db(user=user, instrument_id=test_instrument.instrument_id)

    # Pre-populate a trade to establish a last trade price
    trade = Trades(
        user_id=user.user_id,
        order_id=temp_order.order_id,
        instrument_id=test_instrument.instrument_id,
        price=30000.0,
        quantity=1,
        liquidity="MAKER",
    )
    async_db_session.add(trade)
    await async_db_session.commit()

    initial_escrow = user.escrow_balance

    order_data = {
        "instrument_id": test_instrument.instrument_id,
        "order_type": OrderType.MARKET.value,
        "side": Side.BID.value,
        "quantity": 0.5,
    }

    response = await client.post("/orders/", json=order_data)
    assert response.status_code == 202

    # Verify command was queued
    mock_queue.put_nowait.assert_called_once()

    # Verify user's escrow balance was updated in DB
    await async_db_session.refresh(user)
    expected_escrow_increase = 0.5 * 30000.0
    assert user.escrow_balance == initial_escrow + expected_escrow_increase


@pytest.mark.asyncio(scope="session")
async def test_create_market_order_insufficient_funds(
    async_client, async_db_session, test_instrument
):
    """Tests creating a market order with insufficient funds, expecting a 400 error."""
    client, _, user = async_client

    # Set user balance to be insufficient for the trade
    user.cash_balance = 100.0
    user.escrow_balance = 0.0
    async_db_session.add(user)

    # Creating a temporary order for the trade's foreign key
    temp_order = Orders(
        user_id=user.user_id,
        instrument_id=test_instrument.instrument_id,
        side="bid",
        order_type="limit",
        quantity=1,
        limit_price=100,
    )
    async_db_session.add(temp_order)
    await async_db_session.flush()

    trade = Trades(
        order_id=temp_order.order_id,
        user_id=user.user_id,
        instrument_id=test_instrument.instrument_id,
        price=30000.0,
        quantity=1,
        liquidity="MAKER",
    )
    async_db_session.add(trade)
    await async_db_session.commit()

    order_data = {
        "instrument_id": test_instrument.instrument_id,
        "order_type": "market",
        "side": "bid",
        "quantity": 1,  # requires 1 * 30000 = 30000, user has 100
    }
    response = await client.post("/orders/", json=order_data)

    assert response.status_code == 400
    assert "Invalid cash balance" in response.json()["detail"]


@pytest.mark.asyncio(scope="session")
async def test_create_oco_order(async_client, test_instrument):
    """Tests successful creation of an OCO order."""
    client, mock_queue, _ = async_client
    oco_data = {
        "legs": [
            {
                "instrument_id": test_instrument.instrument_id,
                "order_type": "limit",
                "side": "ask",
                "quantity": 1,
                "limit_price": 31000,
            },
            {
                "instrument_id": test_instrument.instrument_id,
                "order_type": "stop",
                "side": "ask",
                "quantity": 1,
                "stop_price": 29000,
            },
        ]
    }
    response = await client.post("/orders/oco", json=oco_data)

    assert response.status_code == 202
    order_ids = response.json()["order_id"]
    assert isinstance(order_ids, list)
    assert len(order_ids) == 2

    mock_queue.put_nowait.assert_called_once()
    cmd = mock_queue.put_nowait.call_args[0][0]
    assert cmd.command_type == CommandType.NEW_ORDER
    assert isinstance(cmd.data, NewOCOOrder)
    assert len(cmd.data.legs) == 2
    assert cmd.data.legs[0]["limit_price"] == 31000
    assert cmd.data.legs[1]["stop_price"] == 29000


@pytest.mark.asyncio(scope="session")
async def test_create_oto_order(async_client, test_instrument):
    """Tests successful creation of an OTO order."""
    client, mock_queue, _ = async_client
    oto_data = {
        "parent": {
            "instrument_id": test_instrument.instrument_id,
            "order_type": "limit",
            "side": "bid",
            "quantity": 1,
            "limit_price": 29000,
        },
        "child": {
            "instrument_id": test_instrument.instrument_id,
            "order_type": "limit",
            "side": "ask",
            "quantity": 1,
            "limit_price": 31000,
        },
    }
    response = await client.post("/orders/oto", json=oto_data)

    assert response.status_code == 202
    order_ids = response.json()["order_id"]
    assert isinstance(order_ids, list)
    assert len(order_ids) == 2

    mock_queue.put_nowait.assert_called_once()
    cmd = mock_queue.put_nowait.call_args[0][0]
    assert cmd.command_type == CommandType.NEW_ORDER
    assert isinstance(cmd.data, NewOTOOrder)
    assert cmd.data.parent["limit_price"] == 29000
    assert cmd.data.child["limit_price"] == 31000


@pytest.mark.asyncio(scope="session")
async def test_create_otoco_order(async_client, test_instrument):
    """Tests successful creation of an OTOCO order."""
    client, mock_queue, _ = async_client
    otoco_data = {
        "parent": {
            "instrument_id": test_instrument.instrument_id,
            "order_type": "limit",
            "side": "bid",
            "quantity": 1,
            "limit_price": 29000,
        },
        "oco_legs": [
            {
                "instrument_id": test_instrument.instrument_id,
                "order_type": "limit",
                "side": "ask",
                "quantity": 1,
                "limit_price": 31000,
            },
            {
                "instrument_id": test_instrument.instrument_id,
                "order_type": "stop",
                "side": "ask",
                "quantity": 1,
                "stop_price": 28000,
            },
        ],
    }
    response = await client.post("/orders/otoco", json=otoco_data)

    assert response.status_code == 202
    order_ids = response.json()["order_id"]
    assert isinstance(order_ids, list)
    assert len(order_ids) == 3

    mock_queue.put_nowait.assert_called_once()
    cmd = mock_queue.put_nowait.call_args[0][0]
    assert cmd.command_type == CommandType.NEW_ORDER
    assert isinstance(cmd.data, NewOTOCOOrder)
    assert len(cmd.data.oco_legs) == 2
    assert cmd.data.parent["limit_price"] == 29000


@pytest.mark.asyncio(scope="session")
async def test_get_orders_with_pagination_and_filters(
    async_client, async_db_session, test_instrument
):
    """Tests fetching a paginated and filtered list of orders."""
    client, _, user = async_client

    # Create more orders than PAGE_SIZE to test pagination
    for i in range(PAGE_SIZE + 2):
        status = OrderStatus.PLACED if i % 2 == 0 else OrderStatus.FILLED
        side = Side.BID if i < 6 else Side.ASK
        order = Orders(
            user_id=user.user_id,
            instrument_id=test_instrument.instrument_id,
            side=side.value,
            order_type="limit",
            quantity=1,
            limit_price=100 + i,
            status=status.value,
        )
        async_db_session.add(order)
    await async_db_session.commit()

    # Test pagination
    response_p1 = await client.get("/orders/?page=1")
    assert response_p1.status_code == 200
    data_p1 = response_p1.json()
    assert data_p1["page"] == 1
    assert data_p1["size"] == PAGE_SIZE
    assert data_p1["has_next"] is True

    response_p2 = await client.get("/orders/?page=2")
    assert response_p2.status_code == 200
    data_p2 = response_p2.json()
    assert data_p2["page"] == 2
    assert data_p2["size"] == 2
    assert data_p2["has_next"] is False

    # Test filtering. We created 3 placed bid orders.
    response_filtered = await client.get("/orders/?statuses=placed&sides=bid")
    assert response_filtered.status_code == 200
    data_filtered = response_filtered.json()
    assert data_filtered["size"] == 3
    assert all(o["status"] == "placed" and o["side"] == "bid" for o in data_filtered["data"])


@pytest.mark.asyncio(scope="session")
async def test_get_single_order_by_id(async_client, async_db_session, test_instrument):
    """Tests fetching a single order by its ID for the authenticated user."""
    client, _, user = async_client
    order = Orders(
        user_id=user.user_id,
        instrument_id=test_instrument.instrument_id,
        side="bid",
        order_type="limit",
        quantity=5,
        limit_price=100,
    )
    async_db_session.add(order)
    await async_db_session.commit()

    response = await client.get(f"/orders/{order.order_id}")
    assert response.status_code == 200
    assert response.json()["order_id"] == str(order.order_id)


@pytest.mark.asyncio(scope="session")
async def test_get_order_not_found_or_unauthorized(
    async_client, async_db_session, test_instrument
):
    """Tests getting a 404 for a non-existent order or an order belonging to another user."""
    client, _, _ = async_client

    # 1. Non-existent order
    response = await client.get(f"/orders/{uuid.uuid4()}")
    assert response.status_code == 404

    # 2. Order of another user
    fkr = Faker()
    other_user = Users(
        username=fkr.user_name(),
        password="password",
    )
    async_db_session.add(other_user)
    await async_db_session.flush()

    other_order = Orders(
        user_id=other_user.user_id,
        instrument_id=test_instrument.instrument_id,
        side="bid",
        order_type="limit",
        quantity=1,
        limit_price=100,
    )
    async_db_session.add(other_order)
    await async_db_session.commit()

    response = await client.get(f"/orders/{other_order.order_id}")
    assert response.status_code == 404


@pytest.mark.asyncio(scope="session")
async def test_modify_order(async_client, async_db_session, test_instrument):
    """Tests requesting a modification for an active order."""
    client, mock_queue, user = async_client
    order = Orders(
        user_id=user.user_id,
        instrument_id=test_instrument.instrument_id,
        order_type="limit",
        side="bid",
        quantity=1,
        limit_price=100,
        status=OrderStatus.PLACED.value,
    )
    async_db_session.add(order)
    await async_db_session.commit()

    response = await client.put(
        f"/orders/{order.order_id}", json={"limit_price": 105.0}
    )

    assert response.status_code == 202
    assert response.json()["message"] == "Modify request accepted"

    mock_queue.put_nowait.assert_called_once()
    cmd = mock_queue.put_nowait.call_args[0][0]
    assert cmd.command_type == CommandType.MODIFY_ORDER
    assert isinstance(cmd.data, ModifyOrderCommand)
    assert cmd.data.order_id == str(order.order_id)
    assert cmd.data.limit_price == 105.0


@pytest.mark.asyncio(scope="session")
async def test_cancel_single_order(async_client, async_db_session, test_instrument):
    """Tests cancelling a specific order by ID."""
    client, mock_queue, user = async_client
    order = Orders(
        user_id=user.user_id,
        instrument_id=test_instrument.instrument_id,
        side="bid",
        order_type="limit",
        quantity=1,
        limit_price=100,
        status=OrderStatus.PLACED.value,
    )
    async_db_session.add(order)
    await async_db_session.commit()

    response = await client.delete(f"/orders/{order.order_id}")
    assert response.status_code == 202
    assert response.json()["order_id"] == str(order.order_id)

    mock_queue.put_nowait.assert_called_once()
    cmd = mock_queue.put_nowait.call_args[0][0]
    assert cmd.command_type == CommandType.CANCEL_ORDER
    assert isinstance(cmd.data, CancelOrderCommand)
    assert cmd.data.order_id == str(order.order_id)


@pytest.mark.asyncio(scope="session")
async def test_cancel_order_not_found(async_client):
    """Tests that cancelling a non-existent order returns a 404."""
    client, mock_queue, _ = async_client
    response = await client.delete(f"/orders/{uuid.uuid4()}")
    assert response.status_code == 404
    mock_queue.put_nowait.assert_not_called()


@pytest.mark.asyncio(scope="session")
async def test_cancel_all_orders(async_client, async_db_session, test_instrument):
    """Tests cancelling all active orders for the authenticated user."""
    client, mock_queue, user = async_client
    
    active_statuses = [OrderStatus.PLACED, OrderStatus.PARTIALLY_FILLED]
    inactive_statuses = [OrderStatus.FILLED, OrderStatus.CANCELLED]

    for status in active_statuses + inactive_statuses:
        order = Orders(
            user_id=user.user_id,
            instrument_id=test_instrument.instrument_id,
            status=status.value,
            side="bid",
            order_type="limit",
            quantity=1,
            limit_price=100,
        )
        async_db_session.add(order)
    await async_db_session.commit()

    response = await client.delete("/orders/")
    assert response.status_code == 202

    # Should only try to cancel the active orders
    assert mock_queue.put_nowait.call_count == len(active_statuses)