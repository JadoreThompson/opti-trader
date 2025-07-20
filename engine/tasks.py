import json

from datetime import datetime
from pprint import pprint
from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session
from uuid import UUID

from config import CELERY
from db_models import Escrows, OrderEvents, Orders, Users
from enums import Side
from utils.db import get_db_session_sync
from .typing import MODIFY_DEFAULT, EventDict, Event, EventType
from .enums import Tag


def handle_order_filled_event(event: Event, db_sess: Session) -> None:
    """
    Persists the event and updates the user's cash balance accordingly.

    Args:
        ev (Event): _description_
        db_sess (Session): _description_
    """
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
            OrderEvents.event_type == EventType.ORDER_PLACED,
            OrderEvents.order_id == event.order_id,
        )
    ).scalar_one_or_none()

    if opening_price is None:
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
    values = event.model_dump(exclude_unset=True, exclude_none=True)
    values.pop("metadata", None)

    user = db_sess.execute(select(Users).where(Users.user_id == event.user_id)).scalar()

    escrow = db_sess.execute(
        select(Escrows).where(Escrows.order_id == event.order_id)
    ).scalar()

    opening_price = db_sess.execute(
        select(OrderEvents.price)
        .where(
            OrderEvents.event_type == EventType.ORDER_PLACED,
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
    Note: This handler does not adjust escrow, as escrow changes for price
    modifications would require more complex logic (e.g., calculating standing
    quantity) and a more detailed event payload from the engine.
    """
    values_to_update = {}

    if event.limit_price is not MODIFY_DEFAULT:
        values_to_update["limit_price"] = event.limit_price
    if event.take_profit is not MODIFY_DEFAULT:
        values_to_update["take_profit"] = event.take_profit
    if event.stop_loss is not MODIFY_DEFAULT:
        values_to_update["stop_loss"] = event.stop_loss

    if values_to_update:
        db_sess.execute(
            update(Orders)
            .where(Orders.order_id == event.order_id)
            .values(**values_to_update)
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


@CELERY.task
def log_event(event: EventDict):
    # pprint(event)
    # print("", end="\n\n\n")
    with get_db_session_sync() as sess:
        parsed_event = Event(**event)

        if parsed_event.event_type == EventType.ORDER_PLACED:
            handle_order_placed_event(parsed_event, sess)
        elif parsed_event.event_type in (
            EventType.ORDER_PARTIALLY_FILLED,
            EventType.ORDER_FILLED,
        ):
            handle_order_filled_event(parsed_event, sess)
        elif parsed_event.event_type == EventType.ORDER_CANCELLED:
            handle_order_cancelled_event(parsed_event, sess)
        elif parsed_event.event_type == EventType.ORDER_MODIFIED:
            handle_order_modified_event(parsed_event, sess)
        elif parsed_event.event_type == EventType.ORDER_REJECTED:
            handle_order_rejected_event(parsed_event, sess)
