import json
import pytest
import copy

from enums import OrderStatus, OrderType, Side
from tests.utils import (
    # Fixture Imports
    populated_engine,
)


TEST_SIZES = [int(2**i) for i in range(2, 9)] + [512, 1000]


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
    open_positions = list(engine._position_manager._positions.items())

    for i, (order_id, pos) in enumerate(open_positions):
        if pos.entry_order.payload["status"] in (OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED, OrderStatus.CLOSED):
            continue

        if i % n == 0:
            options = [
                "ALL",
                *range(1, pos.entry_order.payload["standing_quantity"] + 1),
            ]
            close_payload = {"order_id": order_id, "quantity": options[i % len(options)]}
            engine.close_order(close_payload)

    final_order_states = {o["order_id"]: o for o in orders_from_engine}
    sanitized_state = sanitize_for_snapshot(final_order_states)
    snapshot.assert_match(
        json.dumps(sanitized_state), "test_close_order_state_snapshot.json"
    )


@pytest.mark.parametrize("populated_engine", TEST_SIZES, indirect=True)
@pytest.mark.parametrize("n", [3, 5])
def test_modify_position_state_snapshot(populated_engine, n, snapshot):
    """
    Tests the modify_position method on a pre-populated engine. It modifies
    every Nth order, testing modifications of both pending limit prices
    and filled positions' TP/SL, then snapshots the final state.
    """
    engine, orders_from_engine = populated_engine

    for i, order_payload in enumerate(list(orders_from_engine)):
        if i % n != 0:
            continue

        status = order_payload["status"]
        order_id = order_payload["order_id"]

        if (
            status == OrderStatus.PENDING
            and order_payload["order_type"] == OrderType.LIMIT
        ):
            new_limit_price = round(order_payload["limit_price"] + 0.25, 2)
            modify_payload = {
                "order_id": order_id,
                "limit_price": new_limit_price,
                "take_profit": order_payload["take_profit"],
                "stop_loss": order_payload["stop_loss"],
            }
            engine.modify_position(modify_payload)

        elif status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED):
            filled_price = order_payload["filled_price"]
            new_tp = round(filled_price + 5.0, 2)
            new_sl = round(filled_price - 5.0, 2)

            if order_payload["side"] == Side.ASK:
                new_tp, new_sl = new_sl, new_tp

            modify_payload = {
                "order_id": order_id,
                "limit_price": None,
                "take_profit": new_tp,
                "stop_loss": new_sl,
            }
            engine.modify_position(modify_payload)

    final_order_states = {o["order_id"]: o for o in orders_from_engine}
    sanitized_state = sanitize_for_snapshot(final_order_states)

    snapshot.assert_match(
        json.dumps(sanitized_state), "test_modify_position_state_snapshot.json"
    )


@pytest.mark.parametrize("populated_engine", TEST_SIZES, indirect=True)
@pytest.mark.parametrize("n", [2, 4])
def test_cancel_order_state_snapshot(populated_engine, n, snapshot):
    """
    Tests the cancel_order method on a pre-populated engine. It iterates
    through orders and cancels every Nth PENDING order, then snapshots
    the final state of all orders to validate the outcome.
    """
    engine, orders_from_engine = populated_engine

    for i, order_payload in enumerate(list(orders_from_engine)):
        if order_payload["status"] == OrderStatus.PENDING:
            if i % n == 0:
                cancel_payload = {"order_id": order_payload["order_id"]}
                engine.cancel_order(cancel_payload)

    final_order_states = {o["order_id"]: o for o in orders_from_engine}
    sanitized_state = sanitize_for_snapshot(final_order_states)

    snapshot.assert_match(
        json.dumps(sanitized_state), "test_cancel_order_state_snapshot.json"
    )
