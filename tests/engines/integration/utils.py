from uuid import UUID

from faker import Faker
import pytest
from sqlalchemy import insert, update
from db_models import Escrows, Orders, Users
from enums import MarketType
from tests.utils import get_db_sess


def apply_escrow(
    amount: float, user_id: str | UUID, order_id: str | UUID, sess
) -> None:
    sess.execute(
        update(Users)
        .values(balance=Users.balance - amount)
        .where(Users.user_id == user_id)
    )
    sess.execute(
        insert(Escrows).values(user_id=user_id, order_id=order_id, balance=amount)
    )
    sess.commit()


def create_user() -> Users:
    fkr = Faker()

    with get_db_sess() as db_sess:
        user = db_sess.execute(
            insert(Users)
            .values(username=fkr.user_name(), password=fkr.password())
            .returning(Users)
        ).scalar()
        db_sess.commit()
    return user


def persist_order(values: dict, market_type: MarketType) -> str:
    """Persists a futures order to the DB and returns its ID."""
    values["market_type"] = MarketType.FUTURES.value
    with get_db_sess() as db_sess:
        order_id = db_sess.execute(
            insert(Orders).values(**values).returning(Orders.order_id)
        ).scalar()
        db_sess.commit()
    return str(order_id)
