# import copy
# import json
# import random
# import pytest
# from engine.typing import CloseRequest, ModifyRequest
# from enums import OrderStatus, OrderType, Side


# TEST_SIZES = [int(2**i) for i in range(2, 9)] + [512, 1000]


# def sanitize_for_snapshot(data: dict) -> dict:
#     """Removes non-deterministic fields from state data for reliable snapshots."""
#     sanitized_data = {}
#     for order_id, state in data.items():
#         s_state = copy.deepcopy(state)
#         s_state.pop("user_id", None)
#         s_state.pop("created_at", None)
#         s_state.pop("closed_at", None)
#         sanitized_data[order_id] = s_state
#     return sanitized_data


# ######## SNAPSHOTS ###########
# @pytest.mark.parametrize("populated_futures_engine", TEST_SIZES, indirect=True)
# def test_place_order_state_snapshot(populated_futures_engine, snapshot):
#     """
#     Validates the final state of all orders after a large population process.
#     This test confirms the cumulative state of placing many orders is correct.
#     """
#     _, orders = populated_futures_engine

#     final_order_states = {o["order_id"]: o for o in orders}
#     sanitized_state = sanitize_for_snapshot(final_order_states)
#     snapshot.assert_match(
#         json.dumps(sanitized_state),
#         snapshot_name="test_place_order_state_snapshot.json",
#     )


# @pytest.mark.parametrize("populated_futures_engine", TEST_SIZES, indirect=True)
# @pytest.mark.parametrize("n", [2, 3])
# def test_close_order_state_snapshot(populated_futures_engine, n, snapshot):
#     """
#     Tests the close_order method on a pre-populated engine, validating the
#     final state of the entire system using a snapshot.
#     """
#     engine, orders_from_engine = populated_futures_engine
#     open_positions = list(engine._positions.items())

#     for i, (order_id, pos) in enumerate(open_positions):
#         if pos.payload["status"] in (
#             OrderStatus.PENDING,
#             OrderStatus.PARTIALLY_FILLED,
#             OrderStatus.CLOSED,
#         ):
#             continue

#         if i % n == 0:
#             options = [
#                 "ALL",
#                 *range(1, pos.payload["standing_quantity"] + 1),
#             ]
#             close_payload = CloseRequest(
#                 **{"order_id": order_id, "quantity": options[i % len(options)]}
#             )
#             engine.close_order(close_payload)

#     final_order_states = {o["order_id"]: o for o in orders_from_engine}
#     sanitized_state = sanitize_for_snapshot(final_order_states)
#     snapshot.assert_match(
#         json.dumps(sanitized_state), "test_close_order_state_snapshot.json"
#     )


# @pytest.mark.parametrize("populated_futures_engine", TEST_SIZES, indirect=True)
# @pytest.mark.parametrize("n", [3, 5])
# def test_modify_position_state_snapshot(populated_futures_engine, n, snapshot):
#     """
#     Tests the modify_position method on a pre-populated engine. It modifies
#     every Nth order, testing modifications of both pending limit prices
#     and filled positions' TP/SL, then snapshots the final state.
#     """
#     engine, orders_from_engine = populated_futures_engine

#     for i, order_payload in enumerate(list(orders_from_engine)):
#         if i % n != 0:
#             continue

#         status = order_payload["status"]
#         order_id = order_payload["order_id"]

#         if (
#             status == OrderStatus.PENDING
#             and order_payload["order_type"] == OrderType.LIMIT
#         ):
#             new_limit_price = round(order_payload["limit_price"] + 0.25, 2)
#             modify_payload = {
#                 "order_id": order_id,
#                 "limit_price": new_limit_price,
#                 "take_profit": order_payload["take_profit"],
#                 "stop_loss": order_payload["stop_loss"],
#             }
#             engine.modify_order(ModifyRequest(**modify_payload))

#         elif status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED):
#             filled_price = order_payload["filled_price"]
#             new_tp = round(filled_price + 5.0, 2)
#             new_sl = round(filled_price - 5.0, 2)

#             if order_payload["side"] == Side.ASK:
#                 new_tp, new_sl = new_sl, new_tp

#             modify_payload = {
#                 "order_id": order_id,
#                 "limit_price": None,
#                 "take_profit": new_tp,
#                 "stop_loss": new_sl,
#             }
#             engine.modify_order(ModifyRequest(**modify_payload))

#     final_order_states = {o["order_id"]: o for o in orders_from_engine}
#     sanitized_state = sanitize_for_snapshot(final_order_states)

#     snapshot.assert_match(
#         json.dumps(sanitized_state), "test_modify_order_state_snapshot.json"
#     )


# @pytest.mark.parametrize("populated_futures_engine", TEST_SIZES, indirect=True)
# @pytest.mark.parametrize("n", [2, 4])
# def test_cancel_order_state_snapshot(populated_futures_engine, n, snapshot):
#     """
#     Tests the cancel_order method on a pre-populated engine. It iterates
#     through orders and cancels every Nth PENDING order, then snapshots
#     the final state of all orders to validate the outcome.
#     """
#     engine, orders_from_engine = populated_futures_engine

#     for i, order_payload in enumerate(list(orders_from_engine)):
#         if order_payload["status"] in (
#             OrderStatus.PENDING,
#             OrderStatus.PARTIALLY_FILLED,
#         ):
#             if i % n == 0:
#                 cancel_payload = {
#                     "order_id": order_payload["order_id"],
#                     "quantity": random.choice(
#                         ["ALL", order_payload["standing_quantity"]]
#                     ),
#                 }
#                 engine.cancel_order(CloseRequest(**cancel_payload))

#     final_order_states = {o["order_id"]: o for o in orders_from_engine}
#     sanitized_state = sanitize_for_snapshot(final_order_states)

#     snapshot.assert_match(
#         json.dumps(sanitized_state), "test_cancel_order_state_snapshot.json"
#     )


# ######## DB ###########


import copy
import json
import random
from uuid import UUID

import pytest
from faker import Faker
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from db_models import Escrows, OrderEvents, Orders, Users, get_default_balance
from engine import FuturesEngine
from engine.typing import CloseRequest, EventType, ModifyRequest
from enums import MarketType, OrderStatus, OrderType, Side
from tests.utils import create_order_simple, get_db_sess

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


def create_user() -> Users:
    """Creates a new user with a default balance and persists it to the DB."""
    with get_db_sess() as db_sess:
        fkr = Faker()
        user = db_sess.execute(
            insert(Users)
            .values(username=fkr.user_name(), password=fkr.password())
            .returning(Users)
        ).scalar()
        db_sess.commit()
    return user


def persist_futures_order(values: dict) -> str:
    """Persists a futures order to the DB and returns its ID."""
    values["market_type"] = MarketType.FUTURES.value
    with get_db_sess() as db_sess:
        order_id = db_sess.execute(
            insert(Orders).values(**values).returning(Orders.order_id)
        ).scalar()
        db_sess.commit()
    return str(order_id)


@pytest.fixture
def engine():
    """Provides a fresh FuturesEngine instance for each test."""
    return FuturesEngine()


# @pytest.fixture
# def patched_log(mocker):
#     """
#     Patches the celery task `log_event.delay` to execute synchronously.
#     This allows testing the database interaction without a live celery worker.
#     """
#     from engine import tasks

#     def side_effect(event_dict):
#         tasks.log_event(event_dict)

#     return mocker.patch("engine.tasks.log_event.delay", side_effect=side_effect)


######## SNAPSHOTS ###########
@pytest.mark.parametrize("populated_futures_engine", TEST_SIZES, indirect=True)
def test_place_order_state_snapshot(populated_futures_engine, snapshot):
    """
    Validates the final state of all orders after a large population process.
    This test confirms the cumulative state of placing many orders is correct.
    """
    _, orders = populated_futures_engine

    final_order_states = {o["order_id"]: o for o in orders}
    sanitized_state = sanitize_for_snapshot(final_order_states)
    snapshot.assert_match(
        json.dumps(sanitized_state),
        snapshot_name="test_place_order_state_snapshot.json",
    )


@pytest.mark.parametrize("populated_futures_engine", TEST_SIZES, indirect=True)
@pytest.mark.parametrize("n", [2, 3])
def test_close_order_state_snapshot(populated_futures_engine, n, snapshot):
    """
    Tests the close_order method on a pre-populated engine, validating the
    final state of the entire system using a snapshot.
    """
    engine, orders_from_engine = populated_futures_engine
    open_positions = list(engine._positions.items())

    for i, (order_id, pos) in enumerate(open_positions):
        if pos.payload["status"] in (
            OrderStatus.PENDING,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.CLOSED,
        ):
            continue

        if i % n == 0:
            options = [
                "ALL",
                *range(1, pos.payload["standing_quantity"] + 1),
            ]
            close_payload = CloseRequest(
                **{"order_id": order_id, "quantity": options[i % len(options)]}
            )
            engine.close_order(close_payload)

    final_order_states = {o["order_id"]: o for o in orders_from_engine}
    sanitized_state = sanitize_for_snapshot(final_order_states)
    snapshot.assert_match(
        json.dumps(sanitized_state), "test_close_order_state_snapshot.json"
    )


@pytest.mark.parametrize("populated_futures_engine", TEST_SIZES, indirect=True)
@pytest.mark.parametrize("n", [3, 5])
def test_modify_position_state_snapshot(populated_futures_engine, n, snapshot):
    """
    Tests the modify_position method on a pre-populated engine. It modifies
    every Nth order, testing modifications of both pending limit prices
    and filled positions' TP/SL, then snapshots the final state.
    """
    engine, orders_from_engine = populated_futures_engine

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
            engine.modify_order(ModifyRequest(**modify_payload))

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
            engine.modify_order(ModifyRequest(**modify_payload))

    final_order_states = {o["order_id"]: o for o in orders_from_engine}
    sanitized_state = sanitize_for_snapshot(final_order_states)

    snapshot.assert_match(
        json.dumps(sanitized_state), "test_modify_order_state_snapshot.json"
    )


@pytest.mark.parametrize("populated_futures_engine", TEST_SIZES, indirect=True)
@pytest.mark.parametrize("n", [2, 4])
def test_cancel_order_state_snapshot(populated_futures_engine, n, snapshot):
    """
    Tests the cancel_order method on a pre-populated engine. It iterates
    through orders and cancels every Nth PENDING order, then snapshots
    the final state of all orders to validate the outcome.
    """
    engine, orders_from_engine = populated_futures_engine

    for i, order_payload in enumerate(list(orders_from_engine)):
        if order_payload["status"] in (
            OrderStatus.PENDING,
            OrderStatus.PARTIALLY_FILLED,
        ):
            if i % n == 0:
                cancel_payload = {
                    "order_id": order_payload["order_id"],
                    "quantity": random.choice(
                        ["ALL", order_payload["standing_quantity"]]
                    ),
                }
                engine.cancel_order(CloseRequest(**cancel_payload))

    final_order_states = {o["order_id"]: o for o in orders_from_engine}
    sanitized_state = sanitize_for_snapshot(final_order_states)

    snapshot.assert_match(
        json.dumps(sanitized_state), "test_cancel_order_state_snapshot.json"
    )


######## DB ###########


def test_order_new_event(engine: FuturesEngine, db_sess: Session, patched_log):
    """
    Scenario: A new limit order is placed but not filled.
    The engine should fire an ORDER_NEW event, which is then persisted.
    """
    user = create_user()
    limit_bid = create_order_simple(
        "",
        side=Side.BID,
        order_type=OrderType.LIMIT,
        instrument="BTC-USD",
        limit_price=100.0,
        quantity=10,
    )
    limit_bid.pop("order_id")
    limit_bid["user_id"] = str(user.user_id)
    order_id = persist_futures_order(limit_bid)
    limit_bid["order_id"] = order_id

    engine.place_order(limit_bid)

    event = db_sess.execute(
        select(OrderEvents).where(OrderEvents.order_id == order_id)
    ).scalar_one_or_none()

    assert event is not None, db_sess.bind.url
    assert event.event_type == EventType.ORDER_NEW.value
    assert event.user_id == user.user_id
    assert event.quantity == 10
    assert event.price == 100.0
    assert event.asset_balance == 0
    assert event.balance == get_default_balance()

    user_balance = db_sess.execute(
        select(Users.balance).where(Users.user_id == user.user_id)
    ).scalar_one_or_none()

    assert user_balance is not None
    assert user_balance == get_default_balance()


def test_order_filled_event(engine: FuturesEngine, db_sess: Session, patched_log):
    """
    Scenario: A limit buy order is on the book and a market sell order fills it.
    The engine should fire ORDER_FILLED events for both orders.
    """
    user = create_user()
    limit_bid = create_order_simple(
        "",
        side=Side.BID,
        order_type=OrderType.LIMIT,
        instrument="BTC-USD",
        limit_price=100.0,
        quantity=10,
    )
    limit_bid.pop("order_id")
    limit_bid["user_id"] = str(user.user_id)
    limit_buy_id = persist_futures_order(limit_bid)
    limit_bid["order_id"] = limit_buy_id

    user2 = create_user()
    market_sell = create_order_simple(
        "",
        side=Side.ASK,
        order_type=OrderType.MARKET,
        instrument="BTC-USD",
        quantity=10,
    )
    market_sell.pop("order_id")
    market_sell["user_id"] = str(user2.user_id)
    market_sell_id = persist_futures_order(market_sell)
    market_sell["order_id"] = market_sell_id

    engine.place_order(limit_bid)
    engine.place_order(market_sell)

    buyer_events = (
        db_sess.execute(
            select(OrderEvents)
            .where(OrderEvents.order_id == limit_buy_id)
            .order_by(OrderEvents.created_at.asc())
        )
        .scalars()
        .all()
    )
    assert len(buyer_events) == 2
    assert buyer_events[0].event_type == EventType.ORDER_NEW
    assert buyer_events[1].event_type == EventType.ORDER_FILLED
    assert buyer_events[1].asset_balance == 10  # open_quantity is now 10

    seller_event = db_sess.execute(
        select(OrderEvents).where(OrderEvents.order_id == market_sell_id)
    ).scalar_one()
    assert seller_event.event_type == EventType.ORDER_FILLED
    assert seller_event.asset_balance == 10


def test_order_closed_event(engine: FuturesEngine, db_sess: Session, patched_log):
    """
    Scenario: A user with a filled position closes it entirely.
    This should result in an ORDER_CLOSED event.
    """
    user1 = create_user()
    market_bid = create_order_simple(
        "",
        side=Side.BID,
        order_type=OrderType.MARKET,
        quantity=10,
    )
    market_bid.pop("order_id")
    market_bid["user_id"] = str(user1.user_id)
    market_bid_id = persist_futures_order(market_bid)
    market_bid["order_id"] = market_bid_id

    user2 = create_user()
    limit_ask = create_order_simple(
        "",
        side=Side.ASK,
        order_type=OrderType.LIMIT,
        limit_price=100.0,
        quantity=10,
    )
    limit_ask.pop("order_id")
    limit_ask["user_id"] = str(user2.user_id)
    limit_ask_id = persist_futures_order(limit_ask)
    limit_ask["order_id"] = limit_ask_id

    engine.place_order(limit_ask)
    engine.place_order(market_bid)

    user3 = create_user()

    resting_bid = create_order_simple(
        "",
        side=Side.BID,
        order_type=OrderType.LIMIT,
        limit_price=105.0,
        quantity=10,
    )
    resting_bid.pop("order_id")
    resting_bid["user_id"] = str(user3.user_id)
    resting_ask_id = persist_futures_order(resting_bid)
    resting_bid["order_id"] = resting_ask_id
    engine._orderbooks[market_bid["instrument"]].set_price(105.0)
    engine.place_order(resting_bid)

    close_request = CloseRequest(order_id=market_bid_id, quantity="ALL")
    engine.close_order(close_request)

    events = (
        db_sess.execute(
            select(OrderEvents)
            .where(OrderEvents.order_id == market_bid_id)
            .order_by(OrderEvents.created_at.asc())
        )
        .scalars()
        .all()
    )
    assert len(events) == 2
    assert events[0].event_type == EventType.ORDER_FILLED
    assert events[0].price == 100.0
    assert events[1].event_type == EventType.ORDER_CLOSED
    assert events[1].price == 105.0
    assert events[1].asset_balance == 0


def test_order_cancelled_event(engine: FuturesEngine, db_sess: Session, patched_log):
    """
    Scenario: A user cancels a portion and then all of a pending limit order.
    """
    user = create_user()
    limit_bid = create_order_simple(
        "", side=Side.BID, order_type=OrderType.LIMIT, quantity=10, limit_price=100.0
    )
    limit_bid.pop("order_id")
    limit_bid["user_id"] = str(user.user_id)
    order_id = persist_futures_order(limit_bid)
    limit_bid["order_id"] = order_id

    engine.place_order(limit_bid)

    db_sess.execute(
        insert(Escrows).values(
            user_id=str(user.user_id),
            order_id=limit_bid["order_id"],
            balance=get_default_balance()
            - (limit_bid["quantity"] * limit_bid["limit_price"]),
        )
    )
    db_sess.commit()

    engine.cancel_order(CloseRequest(order_id=order_id, quantity=4))

    events = (
        db_sess.execute(
            select(OrderEvents)
            .where(OrderEvents.order_id == order_id)
            .order_by(OrderEvents.created_at.asc())
        )
        .scalars()
        .all()
    )
    assert len(events) == 2
    assert events[0].event_type == EventType.ORDER_NEW
    assert events[1].event_type == EventType.ORDER_PARTIALLY_CANCELLED
    assert events[1].quantity == 4
    assert events[1].asset_balance == 0

    engine.cancel_order(CloseRequest(order_id=order_id, quantity="ALL"))
    final_event = db_sess.execute(
        select(OrderEvents)
        .where(OrderEvents.order_id == order_id)
        .order_by(OrderEvents.created_at.desc())
        .limit(1)
    ).scalar_one()
    assert final_event.event_type == EventType.ORDER_CANCELLED
    assert final_event.quantity == 6


def test_order_modified_event(engine: FuturesEngine, db_sess: Session, patched_log):
    """
    Scenario: A user modifies a pending limit order's price and TP/SL.
    This should fire an ORDER_MODIFIED event and update the order in the DB.
    """
    user = create_user()
    limit_bid = create_order_simple(
        "",
        side=Side.BID,
        order_type=OrderType.LIMIT,
        instrument="BTC-USD",
        limit_price=100.0,
        tp_price=110.0,
        sl_price=90.0,
    )
    limit_bid.pop("order_id")
    limit_bid["user_id"] = str(user.user_id)
    order_id = persist_futures_order(limit_bid)
    limit_bid["order_id"] = order_id

    engine.place_order(limit_bid)
    engine._orderbooks["BTC-USD"].set_price(105.0)

    new_limit_price, new_tp, new_sl = 99.0, 120.0, 95.0
    modify_request = ModifyRequest(
        order_id=order_id,
        limit_price=new_limit_price,
        take_profit=new_tp,
        stop_loss=new_sl,
    )
    engine.modify_order(modify_request)

    event = db_sess.execute(
        select(OrderEvents)
        .where(OrderEvents.order_id == order_id)
        .order_by(OrderEvents.created_at.desc())
        .limit(1)
    ).scalar_one()

    assert event.event_type == EventType.ORDER_MODIFIED.value
    assert event.limit_price == new_limit_price
    assert event.take_profit == new_tp
    assert event.stop_loss == new_sl

    db_order = db_sess.execute(
        select(Orders).where(Orders.order_id == order_id)
    ).scalar_one()
    assert db_order.limit_price == new_limit_price
    assert db_order.take_profit == new_tp
    assert db_order.stop_loss == new_sl


def test_order_rejected_event(engine: FuturesEngine, db_sess: Session, patched_log):
    """
    Scenario: A user attempts to close a PENDING order, which is invalid.
    The engine should reject the action and log an ORDER_REJECTED event.
    """
    user = create_user()
    limit_bid = create_order_simple(
        "", side=Side.BID, order_type=OrderType.LIMIT, limit_price=100.0, quantity=10
    )
    limit_bid.pop("order_id")
    limit_bid["user_id"] = str(user.user_id)
    order_id = persist_futures_order(limit_bid)
    limit_bid["order_id"] = order_id

    engine.place_order(limit_bid)
    engine.close_order(CloseRequest(order_id=order_id, quantity="ALL"))

    event = db_sess.execute(
        select(OrderEvents).where(
            OrderEvents.order_id == order_id,
            OrderEvents.event_type == EventType.ORDER_REJECTED.value,
        )
    ).scalar_one()
    assert event is not None
    assert event.user_id == user.user_id
