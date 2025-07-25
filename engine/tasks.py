from sqlalchemy import insert, select, update, func
from sqlalchemy.orm import Session

from config import CELERY
from db_models import Escrows, OrderEvents, Orders, Users
from enums import MarketType, Side
from utils.db import get_db_session_sync
from .typing import MODIFY_SENTINEL, EventDict, Event, EventType
from .enums import Tag


def record_order_event(event: Event, db_sess: Session) -> None:
    """Record a generic order-related event with the user's current balance."""
    values = event.model_dump(exclude_unset=True, exclude_none=True)
    values.pop("metadata", None)

    db_sess.execute(
        insert(OrderEvents).values(
            **values,
            balance=select(Users.balance)
            .where(Users.user_id == event.user_id)
            .scalar_subquery(),
        )
    )
    db_sess.commit()


def handle_futures_order_filled_event(event: Event, db_sess: Session) -> None:
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
        return handle_futures_order_filled_event(event, db_sess)
    return handle_spot_order_filled_event(event, db_sess)


def handle_order_placed_event(event: Event, db_sess: Session) -> None:
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
    print("Updated user balance to ", user.balance)
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

    event_values = event.model_dump(exclude_unset=True, exclude_none=True)
    event_values.pop("metadata", None)

    db_sess.execute(
        insert(OrderEvents).values(
            **event_values,
            balance=select(Users.balance)
            .where(Users.user_id == event.user_id)
            .scalar_subquery(),
        )
    )
    db_sess.commit()


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


def handle_order_rejected_event(event: Event, db_sess: Session) -> None:
    """Persists the order rejection event. No balance changes occur."""
    values = event.model_dump(exclude_unset=True, exclude_none=True)
    values.pop("metadata", None)

    db_sess.execute(
        insert(OrderEvents).values(
            **values,
            balance=select(Users.balance)
            .where(Users.user_id == event.user_id)
            .scalar_subquery(),
        )
    )
    db_sess.commit()


def handle_order_closed_event(event: Event, db_sess: Session) -> None:
    """Persists the order closed event."""
    order_side = db_sess.execute(
        select(Orders.side).where(Orders.order_id == event.order_id)
    ).scalar_one()
    filled_price = db_sess.execute(
        select(Orders.filled_price).where(Orders.order_id == event.order_id)
    ).scalar_one()

    order_price = db_sess.execute(
        select(func.coalesce(Orders.limit_price, Orders.price)).where(
            Orders.order_id == event.order_id
        )
    ).scalar_one()
    
    db_sess.execute(Update(Orders))

    # direction = -1 if order_side == Side.ASK else 1
    # return (event.price - filled_price) * event.quantity * direction
    # db_sess.execute(update(Users.balance))


@CELERY.task
def log_event(event: EventDict):
    with get_db_session_sync() as sess:
        parsed_event = Event(**event)

        # if parsed_event.event_type == EventType.ORDER_NEW:
        #     handle_order_placed_event(parsed_event, sess)
        # elif parsed_event.event_type in (
        #     EventType.ORDER_PARTIALLY_FILLED,
        #     EventType.ORDER_FILLED,
        # ):
        #     handle_order_filled_event(parsed_event, sess)
        # elif parsed_event.event_type == EventType.ORDER_CANCELLED:
        #     handle_order_cancelled_event(parsed_event, sess)
        # elif parsed_event.event_type == EventType.ORDER_MODIFIED:
        #     handle_order_modified_event(parsed_event, sess)
        # elif parsed_event.event_type == EventType.ORDER_REJECTED:
        #     handle_order_rejected_event(parsed_event, sess)

        if parsed_event.event_type in (
            EventType.ORDER_PARTIALLY_FILLED,
            EventType.ORDER_FILLED,
        ):
            handle_order_filled_event(parsed_event, sess)
        elif parsed_event.event_type == EventType.ORDER_CANCELLED:
            handle_order_cancelled_event(parsed_event, sess)
        elif parsed_event.event_type == EventType.ORDER_MODIFIED:
            handle_order_modified_event(parsed_event, sess)
        elif (
            parsed_event.event_type == EventType.ORDER_REJECTED
        ):  # Backwards compatibility, update SpotEngine to use ORDER_NEW_REJECTED or the appropriate event type
            handle_order_rejected_event(parsed_event, sess)
        elif parsed_event.event_type == EventType.ORDER_NEW_REJECTED:
            handle_order_new_rejected_event(parsed_event, sess)
        elif parsed_event.event_type in (
            EventType.ORDER_PARTIALLY_CLOSED,
            EventType.ORDER_CLOSED,
        ):
            # record_order_event(parsed_event, sess)
            handle_order_closed_event(parsed_event, sess)
