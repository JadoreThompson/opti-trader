import uuid
from decimal import Decimal

import pytest
from faker import Faker
from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from src.db_models import Base, Instruments, Users as DBUser, Orders as DBOrder
from src.enums import OrderStatus, OrderType, Side, StrategyType
from src.engine import SpotEngine
from src.engine.event_logger import EventLogger
from src.engine.models import Event
from src.engine.orders import Order
from src.event_handler import EventHandler
from tests.config import DB_URL


@pytest.fixture(scope="session")
def engine():
    return create_engine(DB_URL)


@pytest.fixture(scope="session")
def tables(engine):
    """Session-scoped fixture to create tables."""
    try:
        Base.metadata.create_all(engine)
        yield
    finally:
        Base.metadata.drop_all(engine)


@pytest.fixture(scope="session")
def db_session(engine, tables):
    """Provides a DB session for tests."""
    smaker = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    sess = smaker()
    try:
        yield sess
    finally:
        sess.close()


@pytest.fixture
def user_factory_db(db_session):
    """Factory to create and persist User objects in the test DB."""
    fkr = Faker()

    def _create_user(username=None, cash_balance=10000.0):
        user = DBUser(
            user_id=uuid.uuid4(),
            username=username or fkr.user_name(),
            password="hashed_password",
            cash_balance=cash_balance,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _create_user


@pytest.fixture
def order_factory_db(db_session):
    """Factory to create and persist Order objects in the test DB."""

    def _create_order(user, **kwargs):
        defaults = {
            "order_id": uuid.uuid4(),
            "user_id": user.user_id,
            "instrument_id": "BTC-USD",
            "side": Side.BID.value,
            "order_type": OrderType.LIMIT.value,
            "quantity": 10.0,
            "limit_price": 100.0,
            "status": OrderStatus.PENDING.value,
        }
        defaults.update(kwargs)
        order = DBOrder(**defaults)
        db_session.add(order)
        db_session.commit()
        db_session.refresh(order)
        return order

    return _create_order


@pytest.fixture()
def test_instrument(db_session):
    instrument_id = "BTC-USD"
    instrument = db_session.get(Instruments, instrument_id)
    if not instrument:
        instrument = Instruments(
            instrument_id=instrument_id, symbol="BTC", tick_size=0.001
        )
        db_session.add(instrument)
    return instrument


@pytest.fixture
def event_handler():
    """
    Returns a fresh EventHandler instance for each test.
    Patches the event handler in the engine with a mock versioj
    forcing it to be single threaded.
    """
    return EventHandler()


@pytest.fixture
def order_factory():
    """Factory fixture to create Order objects for testing."""

    def _create_order(
        order_id=None,
        user_id="user1",
        order_type=OrderType.LIMIT,
        side=Side.BID,
        quantity=100,
        price=100.0,
        strategy_type=StrategyType.SINGLE,
    ):
        return Order(
            id_=order_id or str(uuid.uuid4()),
            user_id=user_id,
            strategy_type=strategy_type,
            order_type=order_type,
            side=side,
            quantity=quantity,
            price=price,
        )

    return _create_order


@pytest.fixture
def spot_engine():
    """Fixture to provide a clean SpotEngine instance for a single symbol."""
    engine = SpotEngine(instrument_ids=["BTC-USD"])
    # Add some users to the balance manager
    engine._balance_manager.append("user_taker")
    engine._balance_manager.append("user_maker_1")
    engine._balance_manager.append("user_maker_2")
    return engine


@pytest.fixture
def execution_context(spot_engine):
    """Fixture to get the execution context from the test engine."""
    return spot_engine._ctxs["BTC-USD"]


@pytest.fixture
def mock_execution_context():
    ctx = MagicMock()
    ctx.engine = MagicMock()
    ctx.orderbook = MagicMock()
    ctx.order_store = MagicMock()
    return ctx
