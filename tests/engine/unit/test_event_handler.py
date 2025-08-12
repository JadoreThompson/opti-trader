import json
from decimal import Decimal

import pytest
from sqlalchemy import select

from src.db_models import Events, Orders, Trades, Transactions, Users, AssetBalances
from src.engine.models import Event
from src.enums import (
    EventType,
    OrderType,
    Side,
    OrderStatus,
    TransactionType,
    LiquidityRole,
)


@pytest.mark.parametrize(
    "event_type, expected_status",
    [
        (EventType.ORDER_PARTIALLY_FILLED, OrderStatus.PARTIALLY_FILLED),
        (EventType.ORDER_FILLED, OrderStatus.FILLED),
    ],
)
def test_order_status_update_events(
    user_factory_db,
    order_factory_db,
    test_instrument,
    event_handler,
    db_session,
    event_type,
    expected_status,
):
    """Test that ORDER_PARTIALLY_FILLED and ORDER_FILLED events update the order status."""
    user = user_factory_db()
    order = order_factory_db(user, instrument_id=test_instrument.instrument_id)
    event = Event(
        event_type=event_type.value,
        user_id=str(user.user_id),
        related_id=str(order.order_id),
        details={"quantity": 5, "price": 10},
    )

    event_handler.process_event(db_session, event)

    db_event = db_session.execute(
        select(Events).where(Events.related_id == order.order_id)
    ).scalar_one_or_none()

    assert db_event is not None
    assert db_event.event_type == event_type.value

    db_session.refresh(order)
    assert order.status == expected_status.value


@pytest.mark.parametrize(
    "event_type", [EventType.ORDER_PLACED, EventType.ORDER_MODIFY_REJECTED]
)
def test_generic_log_events(
    user_factory_db, order_factory_db, event_handler, db_session, event_type
):
    """Test events that only create a log entry and have no other side effects."""
    user = user_factory_db()
    order = order_factory_db(user)

    event = Event(
        event_type=event_type.value,
        user_id=str(user.user_id),
        related_id=str(order.order_id),
        details={"reason": "A test reason"},
    )

    event_handler.process_event(db_session, event)

    # Check that only one event log was created
    events = (
        db_session.execute(select(Events).where(Events.related_id == order.order_id))
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].event_type == event_type.value

    # Ensure the original order was not modified
    db_session.refresh(order)
    assert order.status == OrderStatus.PENDING.value


def test_order_modified_event(
    user_factory_db, order_factory_db, event_handler, db_session
):
    """Test that ORDER_MODIFIED event updates the order's price."""
    user = user_factory_db()
    order = order_factory_db(user, order_type=OrderType.LIMIT.value, limit_price=100.0)
    new_price = 105.0
    event = Event(
        event_type=EventType.ORDER_MODIFIED.value,
        user_id=str(user.user_id),
        related_id=str(order.order_id),
        details={"price": new_price},
    )

    event_handler.process_event(db_session, event)

    # Check that the event was logged
    db_event = db_session.execute(
        select(Events).where(Events.related_id == order.order_id)
    ).scalar_one()
    assert db_event.event_type == EventType.ORDER_MODIFIED.value

    # Check that the order's limit price was updated
    db_session.refresh(order)
    assert order.limit_price == new_price


def test_order_cancelled_bid_event(
    user_factory_db, order_factory_db, event_handler, db_session
):
    """Test ORDER_CANCELLED for a BID order refunds cash from escrow."""
    user = user_factory_db(cash_balance=10000.0)
    user.escrow_balance = 1000.0  # Escrow for a 10-unit buy at 100
    db_session.add(user)
    db_session.commit()

    order = order_factory_db(
        user,
        quantity=10,
        limit_price=100.0,
        order_type=OrderType.LIMIT.value,
        side=Side.BID.value,
    )
    event = Event(
        event_type=EventType.ORDER_CANCELLED.value,
        user_id=str(user.user_id),
        related_id=str(order.order_id),
    )

    event_handler.process_event(db_session, event)

    db_session.refresh(user)
    db_session.refresh(order)

    assert order.status == OrderStatus.CANCELLED.value
    assert user.escrow_balance == 0.0

    # A transaction log for the refund is created
    tx = db_session.execute(
        select(Transactions).where(Transactions.related_id == str(order.order_id))
    ).scalar_one()
    assert tx.type == TransactionType.ESCROW.value
    assert tx.amount == 1000.0  # Refund amount for 10 units @ 100 price


def test_order_cancelled_ask_event(
    user_factory_db, order_factory_db, event_handler, db_session, test_instrument
):
    """Test ORDER_CANCELLED for an ASK order refunds assets from escrow."""
    user = user_factory_db()
    order = order_factory_db(
        user,
        quantity=10,
        side=Side.ASK.value,
        executed_quantity=2,
        instrument_id="BTC-USD",
    )

    asset_balance = AssetBalances(
        user_id=user.user_id, instrument_id="BTC-USD", balance=50, escrow_balance=8
    )
    db_session.add(asset_balance)
    db_session.commit()

    event = Event(
        event_type=EventType.ORDER_CANCELLED.value,
        user_id=str(user.user_id),
        related_id=str(order.order_id),
    )

    event_handler.process_event(db_session, event)

    db_session.refresh(order)
    db_session.refresh(asset_balance)

    assert order.status == OrderStatus.CANCELLED.value
    # 8 unfilled units (10 total - 2 filled) are refunded from escrow
    assert asset_balance.escrow_balance == 0.0
    # Main asset balance is untouched by this handler
    assert asset_balance.balance == 50.0


def test_new_trade_buyer_event(
    user_factory_db, order_factory_db, event_handler, db_session, test_instrument
):
    """Test NEW_TRADE event for a buyer, checking all balance and order updates."""
    buyer = user_factory_db(cash_balance=10000.0)
    buyer.escrow_balance = 2000.0  # Escrow for original order
    db_session.add(buyer)

    asset_balance = AssetBalances(
        user_id=buyer.user_id, instrument_id="BTC-USD", balance=5.0
    )
    db_session.add(asset_balance)

    order = order_factory_db(
        buyer,
        side=Side.BID.value,
        quantity=20,
        limit_price=100,
        executed_quantity=5,
        avg_fill_price=99.0,
    )
    db_session.commit()

    trade_details = {
        "quantity": 10,
        "price": 98.0,
        "role": LiquidityRole.TAKER.value,
    }
    event = Event(
        event_type=EventType.NEW_TRADE.value,
        user_id=str(buyer.user_id),
        related_id=str(order.order_id),
        details=trade_details,
    )

    event_handler.process_event(db_session, event)

    db_session.refresh(buyer)
    db_session.refresh(order)
    db_session.refresh(asset_balance)

    # Assert Trade record creation
    trade = db_session.execute(
        select(Trades).where(Trades.order_id == order.order_id)
    ).scalar_one()
    assert trade.quantity == 10 and trade.price == 98.0

    # Assert Order updates
    assert order.executed_quantity == 15  # 5 old + 10 new
    expected_avg_price = (
        (Decimal("5") * Decimal("99.0")) + (Decimal("10") * Decimal("98.0"))
    ) / Decimal("15")
    assert pytest.approx(order.avg_fill_price) == float(expected_avg_price)

    # Assert balance updates
    escrow_deduction = 10 * 100  # Qty * Limit Price
    assert buyer.escrow_balance == 2000.0 - escrow_deduction
    assert buyer.cash_balance == 10000.0 - escrow_deduction
    assert asset_balance.balance == 5.0 + 10  # 5 old + 10 new

    # Assert Transaction creation
    tx = db_session.execute(
        select(Transactions).where(Transactions.related_id == str(trade.trade_id))
    ).scalar_one()
    assert tx.type == TransactionType.TRADE.value
    assert tx.amount == -(10 * 98.0)  # Negative for a buy


def test_new_trade_seller_event(
    user_factory_db, order_factory_db, event_handler, db_session, test_instrument
):
    """Test NEW_TRADE event for a seller, checking all balance and order updates."""
    seller = user_factory_db(cash_balance=5000.0)
    asset_balance = AssetBalances(
        user_id=seller.user_id,
        instrument_id="BTC-USD",
        balance=100.0,
        escrow_balance=20.0,
    )
    db_session.add(asset_balance)
    order = order_factory_db(
        seller, side=Side.ASK.value, quantity=20, instrument_id="BTC-USD"
    )
    db_session.commit()

    trade_details = {
        "quantity": 15,
        "price": 102.0,
        "role": LiquidityRole.MAKER.value,
    }
    event = Event(
        event_type=EventType.NEW_TRADE.value,
        user_id=str(seller.user_id),
        related_id=str(order.order_id),
        details=trade_details,
    )
    event_handler.process_event(db_session, event)

    db_session.refresh(seller)
    db_session.refresh(order)
    db_session.refresh(asset_balance)

    # Assert Trade record creation
    trade = db_session.execute(
        select(Trades).where(Trades.order_id == order.order_id)
    ).scalar_one()
    assert trade.quantity == 15 and trade.price == 102.0

    # Assert Order updates
    assert order.executed_quantity == 15
    assert order.avg_fill_price == 102.0

    # Assert balance updates
    trade_value = 15 * 102.0
    assert seller.cash_balance == 5000.0 + trade_value
    assert asset_balance.escrow_balance == 20.0 - 15
    assert asset_balance.balance == 100.0 - 15

    # Assert Transaction creation
    tx = db_session.execute(
        select(Transactions).where(Transactions.related_id == str(trade.trade_id))
    ).scalar_one()
    assert tx.type == TransactionType.TRADE.value
    assert tx.amount == trade_value
