import json
import pytest
import copy

from uuid import uuid4
from datetime import datetime
from engine import FuturesEngine
from enums import OrderStatus, OrderType, Side
from tests.mocks import MockLock, MockPusher


TEST_SIZES = [int(2**i) for i in range(2, 9)] + [512, 1000]


def create_order(i: int) -> dict:
    is_limit_order = i % 3 == 0
    order_type = OrderType.LIMIT if is_limit_order else OrderType.MARKET
    is_buy = i % 2 == 0
    side = Side.BID if is_buy else Side.ASK
    base_price, price_step, quantity = 100.0, 0.5, 10

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
        "limit_price": None,
        "price": None,
        "closed_at": None,
        "closed_price": None,
        "created_at": datetime.now(),
        "amount": 100,
        "take_profit": base_price + 20 if is_buy and is_limit_order else None,
        "stop_loss": base_price - 10 if is_buy and is_limit_order else None,
    }

    if order_type == OrderType.LIMIT:
        price_offset = (i // 2 * price_step) + 1
        order["limit_price"] = round(
            base_price - price_offset if is_buy else base_price + price_offset, 2
        )
    return order


def sanitize_for_snapshot(data: dict) -> dict:
    """Removes non-deterministic fields from state data for reliable snapshots."""
    sanitized_data = {}
    for order_id, state in data.items():
        s_state = copy.deepcopy(state)
        s_state.pop("user_id", None)
        s_state.pop("created_at", None)
        s_state.pop("closed_at", None)
        sanitized_data[order_id] = s_state
    return sanitized_data


@pytest.fixture
def populated_engine(request):
    """
    Creates and populates a FuturesEngine with a given number of orders.
    This replaces the fixture that used the mock engine.
    """
    num_orders = request.param
    engine = FuturesEngine(MockLock(), MockPusher())
    orders = tuple(create_order(i) for i in range(num_orders))

    for order in orders:
        engine.place_order(order)

    yield engine, orders


@pytest.mark.parametrize("populated_engine", TEST_SIZES, indirect=True)
def test_place_order_state_snapshot(populated_engine, snapshot):
    """
    Validates the final state of all orders after a large population process.
    This test confirms the cumulative state of placing many orders is correct.
    """
    _, orders = populated_engine

    final_order_states = {o["order_id"]: o for o in orders}
    sanitized_state = sanitize_for_snapshot(final_order_states)
    snapshot.assert_match(
        json.dumps(sanitized_state),
        snapshot_name="test_place_order_state_snapshot.json",
    )


@pytest.mark.parametrize("populated_engine", TEST_SIZES, indirect=True)
@pytest.mark.parametrize("n", [2, 3])
def test_close_order_state_snapshot(populated_engine, n, snapshot):
    """
    Tests the close_order method on a pre-populated engine, validating the
    final state of the entire system using a snapshot.
    """
    engine, orders_from_engine = populated_engine
    instrument = "HARNESS_INSTR"

    open_positions = list(engine._position_manager._positions.items())
    for i, (order_id, pos) in enumerate(open_positions):
        if pos.entry_order.payload["status"] == OrderStatus.CLOSED:
            continue

        if i % n == 0:
            close_payload = {"order_id": order_id}
            engine.close_order(close_payload)

    final_order_states = {o["order_id"]: o for o in orders_from_engine}
    sanitized_state = sanitize_for_snapshot(final_order_states)
    snapshot.assert_match(
        json.dumps(sanitized_state), "test_close_order_state_snapshot.json"
    )
