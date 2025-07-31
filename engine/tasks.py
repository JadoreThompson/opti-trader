from json import dumps
from sqlalchemy import insert, select, update, func
from sqlalchemy.orm import Session

from config import (
    CELERY,
    CLIENT_UPDATE_CHANNEL,
    FUTURES_BOOKS_KEY,
    INSTRUMENT_EVENTS_CHANNEL,
    ORDER_EVENTS_CHANNEL,
    REDIS_CLIENT_SYNC,
    SPOT_BOOKS_KEY,
)
from db_models import Escrows, Instruments, MarketData, OrderEvents, Orders, Users
from enums import MarketType, Side, InstrumentEventType
from models import ClientEvent, InstrumentEvent, PriceUpdate, RecentTrade
from utils.db import get_db_session_sync
from utils.utils import get_datetime
from .typing import EventDict, Event, EventType
from .enums import Tag


def record_order_event(event: Event, db_sess: Session) -> None:
    """Record a generic order-related event with the user's current balance."""
    values = event.model_dump(exclude_unset=True, exclude_none=True)
    values.pop("metadata", None)

    db_sess.execute(
        insert(OrderEvents).values(
            **values,
            balance=(
                select(Users.balance)
                .where(Users.user_id == event.user_id)
                .scalar_subquery()
            ),
        )
    )
    db_sess.commit()


def handle_spot_order_filled_event(event: Event, db_sess: Session) -> None:
    order = db_sess.execute(
        select(Orders).where(Orders.order_id == event.order_id)
    ).scalar()
    if not order:
        return

    user = db_sess.execute(select(Users).where(Users.user_id == event.user_id)).scalar()

    escrow = db_sess.execute(
        select(Escrows).where(Escrows.order_id == event.order_id)
    ).scalar()

    opening_price = db_sess.execute(
        select(OrderEvents.price).where(
            OrderEvents.event_type == EventType.ORDER_NEW,
            OrderEvents.order_id == event.order_id,
        )
    ).scalar_one_or_none()

    if opening_price is None:  # look for the filled price from Orders instead.
        opening_price = db_sess.execute(
            select(OrderEvents.price)
            .where(
                OrderEvents.event_type.in_(
                    (EventType.ORDER_PARTIALLY_FILLED, EventType.ORDER_FILLED)
                ),
                OrderEvents.order_id == event.order_id,
            )
            .order_by(OrderEvents.created_at.asc())
            .limit(1)
        ).scalar()

    if opening_price is None:
        opening_price = event.price

    dumped_event = event.model_dump(exclude_unset=True, exclude_none=True)
    dumped_event.pop("metadata", None)

    if (
        event.metadata
        and event.metadata.get("tag") in (Tag.STOP_LOSS, Tag.TAKE_PROFIT)
        or order.side == Side.ASK
    ):
        original_value = opening_price * event.quantity
        new_value = event.price * event.quantity
        diff = abs(original_value - new_value)

        if new_value < original_value:
            escrow.balance -= diff
            user.balance -= diff
        elif new_value > original_value:
            escrow.balance += diff
            user.balance += diff

    db_sess.execute(insert(OrderEvents).values(**dumped_event, balance=user.balance))
    db_sess.commit()


def handle_order_filled_event(event: Event, db_sess: Session) -> None:
    """
    Persists the event and updates the user's cash balance accordingly.

    Args:
        ev (Event): _description_
        db_sess (Session): _description_
    """
    if event.metadata["market_type"] == MarketType.FUTURES:
        return record_order_event(event, db_sess)
    return handle_spot_order_filled_event(event, db_sess)


def handle_order_cancelled_event(event: Event, db_sess: Session) -> None:
    """
    Handle an order-cancelled event and adjust balances.

    Uses the opening price of the order when calculating the amount to refund,
    because the user initially committed funds based on that opening price.

    Args:
        event (Event): The cancelled order event containing order details.
        db_sess (Session): Active database session used for queries and updates.
    """
    values = event.model_dump(exclude_unset=True, exclude_none=True)
    values.pop("metadata", None)

    user = db_sess.execute(select(Users).where(Users.user_id == event.user_id)).scalar()

    escrow = db_sess.execute(
        select(Escrows).where(Escrows.order_id == event.order_id)
    ).scalar()

    opening_price = db_sess.execute(
        select(OrderEvents.price)
        .where(
            OrderEvents.event_type == EventType.ORDER_NEW,
            OrderEvents.order_id == event.order_id,
        )
        .order_by(OrderEvents.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()

    amount = event.quantity * opening_price
    user.balance += amount
    escrow.balance -= amount
    db_sess.execute(insert(OrderEvents).values(**values, balance=user.balance))
    db_sess.commit()


def handle_order_modified_event(event: Event, db_sess: Session) -> None:
    """
    Persists the event and updates the order's attributes in the database.
    Note: This handler does not adjust escrow.

    Args:
        event (Event): The order modification event containing updated details.
        db_sess (Session): Active database session used for queries and updates.
    """
    db_sess.execute(
        update(Orders)
        .where(Orders.order_id == event.order_id)
        .values(
            limit_price=event.limit_price,
            take_profit=event.take_profit,
            stop_loss=event.stop_loss,
        )
    )

    record_order_event(event, db_sess)


def handle_order_new_rejected_event(event: Event, db_sess: Session) -> None:
    """
    Handle an event where a new order submission was rejected.

    Restores any funds that were previously placed into escrow back to the
    user's balance, resets the escrow balance for the associated order, and
    records the rejection event in the order events table.

    Args:
        event (Event): The rejected order event containing the user and order identifiers.
        db_sess (Session): The active database session used to query and update records.

    Side Effects:
        Updates the `Escrows` and `Users` tables to reflect the restored balance,
        and inserts a new record into `OrderEvents` with the updated user balance.
    """
    escrow_balance = db_sess.execute(
        select(Escrows.balance).where(
            Escrows.user_id == event.user_id, Escrows.order_id == event.order_id
        )
    ).scalar()

    db_sess.execute(
        update(Escrows)
        .values(balance=0)
        .where(Escrows.user_id == event.user_id, Escrows.order_id == event.order_id)
    )

    user_balance = db_sess.execute(
        update(Users)
        .values(balance=Users.balance + escrow_balance)
        .where(Users.user_id == event.user_id)
        .returning(Users.balance)
    ).scalar()

    values = event.model_dump(exclude_unset=True, exclude_none=True)
    values.pop("metadata", None)
    db_sess.execute(insert(OrderEvents).values(**values, balance=user_balance))


def handle_order_closed_event(event: Event, db_sess: Session) -> None:
    """
    Persists the order closed event. to be called when FUTURES order
    is closed.
    """
    order_side = db_sess.execute(
        select(Orders.side).where(Orders.order_id == event.order_id)
    ).scalar_one()

    filled_price = db_sess.execute(
        select(Orders.filled_price).where(Orders.order_id == event.order_id)
    ).scalar_one()

    submission_price = db_sess.execute(
        select(func.coalesce(Orders.limit_price, Orders.price)).where(
            Orders.order_id == event.order_id
        )
    ).scalar_one()

    escrow_obj = db_sess.execute(
        select(Escrows).where(Escrows.order_id == event.order_id)
    ).scalar()

    escrow_balance = submission_price * event.quantity
    direction = -1 if order_side == Side.ASK else 1
    pnl = (event.price - filled_price) * event.quantity * direction
    owed_balance = escrow_balance + pnl

    escrow_obj.balance -= escrow_balance

    user_balance = db_sess.execute(
        select(Users.balance).where(Users.user_id == event.user_id)
    ).scalar()

    user_balance = db_sess.execute(
        update(Users)
        .values(balance=Users.balance + owed_balance)
        .where(Users.user_id == event.user_id)
        .returning(Users.balance)
    ).scalar()

    db_sess.execute(
        insert(OrderEvents).values(
            **event.model_dump(
                exclude_unset=True, exclude_none=True, exclude={"metadata"}
            ),
            balance=user_balance,
        )
    )

    db_sess.commit()


@CELERY.task
def log_event(event: EventDict):
    fill_events = (
        EventType.ORDER_PARTIALLY_FILLED,
        EventType.ORDER_FILLED,
        EventType.ORDER_PARTIALLY_CLOSED,
        EventType.ORDER_CLOSED,
    )

    with get_db_session_sync() as sess:
        parsed_event = Event(**event)

        if parsed_event.event_type == EventType.ORDER_CANCELLED:
            handle_order_cancelled_event(parsed_event, sess)
        elif parsed_event.event_type == EventType.ORDER_MODIFIED:
            handle_order_modified_event(parsed_event, sess)
        elif parsed_event.event_type == EventType.ORDER_NEW_REJECTED:
            handle_order_new_rejected_event(parsed_event, sess)
        elif parsed_event.event_type in (
            EventType.ORDER_PARTIALLY_CLOSED,
            EventType.ORDER_CLOSED,
        ):
            handle_order_closed_event(parsed_event, sess)
        else:
            record_order_event(parsed_event, sess)

        if fill_events:
            instrument = sess.execute(
                select(Orders.instrument).where(
                    Orders.order_id == parsed_event.order_id
                )
            ).scalar()

            sess.execute(
                insert(MarketData).values(
                    price=parsed_event.price,
                    instrument=instrument,
                    instrument_id=(
                        select(Instruments.instrument_id).where(
                            Instruments.instrument == instrument
                        )
                    ).scalar_subquery(),
                )
            )
            sess.commit()

        instrument, market_type, side = sess.execute(
            select(Orders.instrument, Orders.market_type, Orders.side).where(
                Orders.order_id == parsed_event.order_id
            )
        ).first()

    # Instrument Update
    if parsed_event.event_type in fill_events:
        market_type = parsed_event.metadata.get("market_type")
        if market_type is not None:
            REDIS_CLIENT_SYNC.hset(
                (
                    FUTURES_BOOKS_KEY
                    if market_type == MarketType.FUTURES
                    else SPOT_BOOKS_KEY
                ),
                instrument,
                parsed_event.price,
            )

        REDIS_CLIENT_SYNC.publish(
            INSTRUMENT_EVENTS_CHANNEL,
            InstrumentEvent[PriceUpdate](
                event_type=InstrumentEventType.PRICE_UPDATE.value,
                instrument=instrument,
                data=PriceUpdate(price=parsed_event.price, market_type=market_type),
            ).model_dump_json(),
        )

        if parsed_event.quantity is not None:
            REDIS_CLIENT_SYNC.publish(
                INSTRUMENT_EVENTS_CHANNEL,
                InstrumentEvent[RecentTrade](
                    event_type=InstrumentEventType.RECENT_TRADE.value,
                    instrument=instrument,
                    data=RecentTrade(
                        price=parsed_event.price,
                        quantity=parsed_event.quantity,
                        side=side,
                        # time=get_datetime(),
                        time=get_datetime().strftime("%I:%M:%S"),
                    ),
                ).model_dump_json(),
            )

    # Order Update
    REDIS_CLIENT_SYNC.publish(
        # CLIENT_UPDATE_CHANNEL,
        ORDER_EVENTS_CHANNEL,
        ClientEvent(
            event_type=parsed_event.event_type.value,
            order_id=parsed_event.order_id,
            user_id=parsed_event.user_id,
            data=parsed_event.model_dump(exclude={"event_type"}),
        ).model_dump_json(),
    )
