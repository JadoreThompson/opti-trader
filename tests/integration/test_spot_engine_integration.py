from pprint import pprint
import pytest

from contextlib import contextmanager
from faker import Faker
from uuid import UUID, uuid4
from sqlalchemy import insert, select, update
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from config import TEST_DB_ENGINE
from db_models import Base, Escrows, OrderEvents, Orders, Users
from engine.tasks import log_event
from engine.typing import EventType
from enums import MarketType, OrderType, Side
from engine import SpotEngine
from tests.utils import create_order_simple


@contextmanager
def get_db_sess() -> Generator[Session, None, None]:
    smaker = sessionmaker(bind=TEST_DB_ENGINE, class_=Session, expire_on_commit=False)
    with smaker() as sess:
        yield sess


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
            update(Users).values(Users.balance - amount).where(Users.user_id == user_id)
        )
        sess.execute(
            insert(Escrows).values(user_id=user_id, order_id=order_id, balance=amount)
        )
        sess.commit()


class MockCelery:
    def __init__(self, func) -> None:
        self.func = func

    def delay(self, *args, **kwargs):
        self.func(*args, **kwargs)


@pytest.fixture
def db() -> Generator[None, None, None]:
    try:
        Base.metadata.create_all(bind=TEST_DB_ENGINE)
        yield
    finally:
        Base.metadata.drop_all(bind=TEST_DB_ENGINE)
        ...


@pytest.fixture
def db_sess(db):
    with get_db_sess() as sess:
        yield sess


@pytest.fixture
def patched_log(monkeypatch):
    mock_log_event = MockCelery(log_event)
    monkeypatch.setattr("engine.matching_engines.spot_engine.log_event", mock_log_event)
    monkeypatch.setattr("engine.tasks.get_db_session_sync", get_db_sess)


def test_order_placed_event(engine: SpotEngine, db_sess: Session, patched_log):
    """
    Scenario: No best ask so limit is placed triggering ORDER_PLACED event.
    """
    instrument = "instr"
    buy_order = create_order_simple(
        "", Side.BID, OrderType.LIMIT, instrument=instrument, limit_price=99.0
    )
    user_id = create_user()
    buy_order["user_id"] = user_id
    buy_order.pop("order_id")
    buy_order["order_id"] = persist_order(buy_order)

    engine.place_order(buy_order)

    event = db_sess.execute(
        select(OrderEvents).where(OrderEvents.order_id == buy_order["order_id"])
    ).scalar_one_or_none()

    assert event is not None
    assert event.event_type == EventType.ORDER_PLACED
    assert event.quantity == buy_order["quantity"]


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
    engine._balance_manager._users[market_sell["user_id"]] = market_sell["quantity"]

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

    assert len(events) == 2
    assert events[0].event_type == EventType.ORDER_PLACED
    assert events[0].asset_balance == 0
    assert events[0].balance == 10_000
    assert events[1].event_type == EventType.ORDER_FILLED
    assert events[1].asset_balance == 10
    assert events[1].balance == 10_000


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
    engine._balance_manager._users[market_sell["user_id"]] = market_sell["quantity"]

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

    assert len(events) == 2
    assert events[0].event_type == EventType.ORDER_PLACED
    assert events[0].asset_balance == 0
    assert events[0].balance == 10_000
    assert events[1].event_type == EventType.ORDER_PARTIALLY_FILLED
    assert events[1].asset_balance == 5
    assert events[1].balance == 10_000
