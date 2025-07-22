import pytest

from faker import Faker
from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session
from uuid import UUID

from db_models import Escrows, OrderEvents, Orders, Users, get_default_balance
from engine.balance_manager import BalanceManager
from engine.orderbook import OrderBook
from enums import MarketType, OrderType, Side
from engine import SpotEngine
from engine.typing import CloseRequest, EventType, ModifyRequest
from tests.utils import create_order_simple, get_db_sess


def create_user() -> str:
    with get_db_sess() as db_sess:
        fkr = Faker()
        user_id = db_sess.execute(
            insert(Users)
            .values(username=fkr.user_name(), password=fkr.password())
            .returning(Users.user_id)
        ).scalar()
        db_sess.commit()
    return str(user_id)


def persist_order(values: dict) -> str:
    values["market_type"] = MarketType.SPOT.value
    with get_db_sess() as db_sess:
        order_id = db_sess.execute(
            insert(Orders).values(**values).returning(Orders.order_id)
        ).scalar()
        db_sess.commit()
    return str(order_id)


def apply_escrow(amount: float, user_id: str | UUID, order_id: str | UUID):
    with get_db_sess() as sess:
        sess.execute(
            update(Users)
            .values(balance=Users.balance - amount)
            .where(Users.user_id == user_id)
        )
        sess.execute(
            insert(Escrows).values(user_id=user_id, order_id=order_id, balance=amount)
        )
        sess.commit()


@pytest.fixture
def engine():
    """Provides a fresh SpotEngine instance for each test."""
    return SpotEngine()


def test_order_placed_event(engine: SpotEngine, db_sess: Session, patched_log):
    """
    Scenario: No best ask so limit is placed triggering ORDER_PLACED event.
    """
    instrument = "instr"
    buy_order = create_order_simple(
        "", Side.BID, OrderType.LIMIT, instrument=instrument, limit_price=100.0
    )
    user_id = create_user()
    buy_order["user_id"] = user_id
    buy_order.pop("order_id")
    buy_order["order_id"] = persist_order(buy_order)
    apply_escrow(
        buy_order["limit_price"] * buy_order["quantity"],
        buy_order["user_id"],
        buy_order["order_id"],
    )

    engine.place_order(buy_order)

    event = db_sess.execute(
        select(OrderEvents).where(OrderEvents.order_id == buy_order["order_id"])
    ).scalar_one()
    user_balance = db_sess.execute(
        select(Users.balance).where(Users.user_id == buy_order["user_id"])
    ).scalar()

    assert event.event_type == EventType.ORDER_PLACED
    assert event.quantity == buy_order["quantity"]
    assert user_balance == 9000.0


def test_order_filled_event(engine: SpotEngine, db_sess: Session, patched_log):
    """
    Scenario: No best ask so limit is placed triggering ORDER_PLACED event.
    Market ask comes in at price level triggering ORDER_FILLED on both
    limit bid and market ask.
    """
    limit_buy = create_order_simple(
        "",
        Side.BID,
        OrderType.LIMIT,
        quantity=10,
        limit_price=100.0,
    )
    user_id = create_user()
    limit_buy["user_id"] = user_id
    limit_buy.pop("order_id")
    limit_buy["order_id"] = persist_order(limit_buy)
    apply_escrow(
        limit_buy["limit_price"] * limit_buy["quantity"],
        limit_buy["user_id"],
        limit_buy["order_id"],
    )

    market_sell = create_order_simple(
        "",
        Side.ASK,
        OrderType.MARKET,
        quantity=10,
    )
    user_id = create_user()
    market_sell["user_id"] = user_id
    market_sell.pop("order_id")
    market_sell["order_id"] = persist_order(market_sell)
    _, balance_manager = engine._orderbooks.setdefault(
        market_sell["instrument"], (OrderBook(), BalanceManager())
    )
    balance_manager._users[market_sell["user_id"]] = market_sell["quantity"]

    engine.place_order(limit_buy)
    engine.place_order(market_sell)

    events = (
        db_sess.execute(
            select(OrderEvents)
            .where(OrderEvents.order_id == limit_buy["order_id"])
            .order_by(OrderEvents.created_at.asc())
        )
        .scalars()
        .all()
    )

    escrow_balance = db_sess.execute(
        select(Escrows.balance).where(Escrows.order_id == limit_buy["order_id"])
    ).scalar()

    assert len(events) == 2
    assert events[0].event_type == EventType.ORDER_PLACED
    assert events[0].asset_balance == 0
    assert events[0].balance == 9000.0
    assert events[1].event_type == EventType.ORDER_FILLED
    assert events[1].asset_balance == 10
    assert events[1].balance == 9000.0
    assert escrow_balance == 1000.0


def test_order_partially_filled_event(
    engine: SpotEngine, db_sess: Session, patched_log
):
    limit_buy = create_order_simple(
        "",
        Side.BID,
        OrderType.LIMIT,
        quantity=10,
        limit_price=100.0,
    )
    user_id = create_user()
    limit_buy["user_id"] = user_id
    limit_buy.pop("order_id")
    limit_buy["order_id"] = persist_order(limit_buy)

    apply_escrow(
        limit_buy["limit_price"] * limit_buy["quantity"],
        limit_buy["user_id"],
        limit_buy["order_id"],
    )

    market_sell = create_order_simple(
        "",
        Side.ASK,
        OrderType.MARKET,
        quantity=5,
    )
    user_id = create_user()
    market_sell["user_id"] = user_id
    market_sell.pop("order_id")
    market_sell["order_id"] = persist_order(market_sell)
    _, balance_manager = engine._orderbooks.setdefault(
        market_sell["instrument"], (OrderBook(), BalanceManager())
    )
    balance_manager._users[market_sell["user_id"]] = market_sell["quantity"]

    engine.place_order(limit_buy)
    engine.place_order(market_sell)

    events = (
        db_sess.execute(
            select(OrderEvents)
            .where(OrderEvents.order_id == limit_buy["order_id"])
            .order_by(OrderEvents.created_at.asc())
        )
        .scalars()
        .all()
    )
    escrow_balance = db_sess.execute(
        select(Escrows.balance).where(Escrows.order_id == limit_buy["order_id"])
    ).scalar()
    user_balance = db_sess.execute(
        select(Users.balance).where(Users.user_id == limit_buy["user_id"])
    ).scalar()

    assert len(events) == 2
    assert events[0].event_type == EventType.ORDER_PLACED
    assert events[0].asset_balance == 0
    assert events[0].balance == 9000.0
    assert events[1].event_type == EventType.ORDER_PARTIALLY_FILLED
    assert events[1].asset_balance == 5
    assert events[1].balance == 9000.0
    assert escrow_balance == 1000.0
    assert user_balance == 9000.0


def test_order_cancelled_event(engine: SpotEngine, db_sess, patched_log):
    limit_buy = create_order_simple(
        "",
        Side.BID,
        OrderType.LIMIT,
        quantity=10,
        limit_price=100.0,
    )
    user_id = create_user()
    limit_buy["user_id"] = user_id
    limit_buy.pop("order_id")
    limit_buy["order_id"] = persist_order(limit_buy)
    apply_escrow(
        limit_buy["quantity"] * limit_buy["limit_price"],
        limit_buy["user_id"],
        limit_buy["order_id"],
    )
    engine.place_order(limit_buy)

    # ORDER_PLACED
    events = (
        db_sess.execute(
            select(OrderEvents)
            .where(OrderEvents.order_id == limit_buy["order_id"])
            .order_by(OrderEvents.created_at.asc())
        )
        .scalars()
        .all()
    )
    escrow_balance = db_sess.execute(
        select(Escrows.balance).where(Escrows.order_id == limit_buy["order_id"])
    ).scalar()
    user_balance = db_sess.execute(
        select(Users.balance).where(Users.user_id == limit_buy["user_id"])
    ).scalar()

    balance = get_default_balance() - escrow_balance
    assert len(events) == 1
    assert events[0].event_type == EventType.ORDER_PLACED
    assert events[0].asset_balance == 0
    assert events[0].balance == balance
    assert escrow_balance == 1000.0
    assert user_balance == 9000.0

    # ORDER_CANCELLED
    cancel_request = CloseRequest(order_id=limit_buy["order_id"], quantity=5)
    engine.cancel_order(cancel_request)

    events = (
        db_sess.execute(
            select(OrderEvents)
            .where(OrderEvents.order_id == limit_buy["order_id"])
            .order_by(OrderEvents.created_at.asc())
        )
        .scalars()
        .all()
    )
    escrow_balance = db_sess.execute(
        select(Escrows.balance).where(Escrows.order_id == limit_buy["order_id"])
    ).scalar()
    user_balance = db_sess.execute(
        select(Users.balance).where(Users.user_id == limit_buy["user_id"])
    ).scalar()

    balance += cancel_request.quantity * limit_buy["limit_price"]
    assert len(events) == 2
    assert events[1].event_type == EventType.ORDER_CANCELLED
    assert events[1].asset_balance == 0
    assert events[1].balance == balance
    assert escrow_balance == 500.0
    assert user_balance == 9500.0


def test_order_modified_event(engine: SpotEngine, db_sess: Session, patched_log):
    """
    Scenario: A resting limit order's price is modified.
    An ORDER_MODIFIED event should be fired, and the engine state updated,
    even if the event is not persisted by the task handler.
    """
    limit_buy = create_order_simple(
        "",
        Side.BID,
        OrderType.LIMIT,
        quantity=10,
        limit_price=100.0,
    )
    user_id = create_user()
    limit_buy["user_id"] = user_id
    limit_buy.pop("order_id")
    limit_buy["order_id"] = persist_order(limit_buy)
    apply_escrow(
        limit_buy["quantity"] * limit_buy["limit_price"],
        limit_buy["user_id"],
        limit_buy["order_id"],
    )

    engine.place_order(limit_buy)

    new_limit_price = 99.0
    modify_request = ModifyRequest(
        order_id=limit_buy["order_id"], limit_price=new_limit_price
    )
    engine.modify_order(modify_request)

    event = db_sess.execute(
        select(OrderEvents)
        .where(OrderEvents.order_id == limit_buy["order_id"])
        .order_by(OrderEvents.created_at.desc())
        .limit(1)
    ).scalar()

    assert event.event_type == EventType.ORDER_MODIFIED.value
    assert event.limit_price == new_limit_price

    events = (
        db_sess.execute(select(OrderEvents).order_by(OrderEvents.created_at.asc()))
        .scalars()
        .all()
    )
    assert len(events) == 2
    assert events[0].event_type == EventType.ORDER_PLACED


def test_order_rejected_event(engine: SpotEngine, db_sess: Session, patched_log):
    """
    Scenario: A user attempts to sell more assets than they own.
    The engine should reject the order and log an ORDER_REJECTED event.
    """
    sell_order = create_order_simple(
        "",
        Side.ASK,
        OrderType.MARKET,
        quantity=10,
    )
    user_id = create_user()
    sell_order["user_id"] = user_id
    sell_order.pop("order_id")
    sell_order["order_id"] = persist_order(sell_order)

    engine.place_order(sell_order)

    event = db_sess.execute(
        select(OrderEvents).where(OrderEvents.order_id == sell_order["order_id"])
    ).scalar_one()

    assert event.event_type == EventType.ORDER_REJECTED
    assert event.user_id == UUID(user_id)
    assert event.asset_balance == 0
    assert event.balance == get_default_balance()

    user_balance = db_sess.execute(
        select(Users.balance).where(Users.user_id == user_id)
    ).scalar()
    assert user_balance == get_default_balance()
