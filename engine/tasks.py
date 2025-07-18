import json

from datetime import datetime
from pprint import pprint
from sqlalchemy import insert, select
from sqlalchemy.orm import Session
from uuid import UUID

from config import CELERY
from db_models import Escrows, OrderEvents, Orders, Users
from enums import Side
from utils.db import get_db_session_sync
from .typing import EventDict, Event, EventType
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

    escrow_balance = db_sess.execute(
        select(Escrows.balance).where(Escrows.order_id == event.order_id)
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
    dumped_event.pop("metadata")

    if (
        event.metadata.get("tag") in (Tag.STOP_LOSS, Tag.TAKE_PROFIT)
        or order.side == Side.ASK
    ):
        original_value = opening_price * event.quantity
        new_value = event.price * event.quantity
        diff = abs(original_value - new_value)

        if new_value < original_value:
            escrow_balance -= diff
            user.balance -= diff
        elif new_value > original_value:
            escrow_balance += diff
            user.balance += diff

    db_sess.execute(insert(OrderEvents).values(**dumped_event, balance=user.balance))
    db_sess.commit()


def handle_order_placed_event(event: Event, db_sess: Session):
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
    pprint(event)
    print("", end="\n\n\n")
    with get_db_session_sync() as sess:
        parsed_event = Event(**event)

        if parsed_event.event_type == EventType.ORDER_PLACED:
            handle_order_placed_event(parsed_event, sess)
        elif parsed_event.event_type in (
            EventType.ORDER_PARTIALLY_FILLED,
            EventType.ORDER_FILLED,
        ):
            handle_order_filled_event(parsed_event, sess)
