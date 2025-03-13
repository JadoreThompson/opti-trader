import sqlalchemy

from sqlalchemy import select
from typing import Optional

from ...middleware import JWT
from .model import AUM
from db_models import Orders, Users
from enums import OrderStatus
from utils.db import get_db_session


async def calculate_aum(
    jwt: JWT, username: Optional[str] = None
) -> list[Optional[AUM]]:
    """
    Calculates the total value of assets held for the specified
    user.

    Args:
        user_id (str)
        username (Optional[str], optional):  Defaults to None.

    Returns:
        (list[Optional[AUM]])
    """
    query = (
        select(
            sqlalchemy.sql.func.sum(Orders.amount),
            Orders.instrument,
            sqlalchemy.sql.func.sum(Orders.realised_pnl),
            sqlalchemy.sql.func.sum(Orders.unrealised_pnl),
        )
        .where(
            Orders.status.not_in(
                (OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED, OrderStatus.CLOSED)
            )
        )
        .group_by(Orders.instrument)
    )

    if username is None or username == jwt["username"]:
        query = query.where(Orders.user_id == jwt["sub"])
    else:
        query = query.where(
            Orders.user_id == select(Users.user_id).where(Users.username == username)
        )

    async with get_db_session() as sess:
        res = await sess.execute(query)
        res = res.all()

    return [AUM(value=item[0] + item[2] + item[3], name=item[1]) for item in res]
