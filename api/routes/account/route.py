from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Annotated, Optional
from sqlalchemy import select, update

from config import DB_LOCK
from db_models import Orders, Users
from enums import MarketType, OrderStatus
from utils.db import get_db_session
from .model import Profile, UpdateProfile
from ...middleware import JWT, verify_jwt_http
from ..order.models import OrderRead, PaginatedOrders

account = APIRouter(prefix="/account", tags=["account"])


@account.get("")
async def get_account(
    username: Optional[str] = None, jwt: JWT = Depends(verify_jwt_http)
) -> Profile:
    query = select(Users)

    if username is None:
        query = query.where(Users.user_id == jwt["sub"])
    else:
        query = query.where(Users.username == username)

    async with DB_LOCK:
        async with get_db_session() as sess:
            res = await sess.execute(query)
            user: Optional[Users] = res.scalar()

    if not user:
        raise HTTPException(status_code=404, detail="User doesn't exist")

    return Profile(**vars(user), is_user=jwt["username"] == user.username)


@account.put("/update")
async def update_account(body: UpdateProfile, jwt: JWT = Depends(verify_jwt_http)):
    data: dict = body.model_dump()

    if all(key and data[key] is None for key in data):
        raise HTTPException(
            status_code=204,
        )

    async with get_db_session() as sess:
        await sess.execute(
            update(Users).values(**data).where(Users.user_id == jwt["sub"])
        )
        await sess.commit()


@account.get("/orders")
async def get_orders(
    username: str = None,
    instrument: str = None,
    market_type: MarketType = MarketType.FUTURES,
    status: Annotated[list[OrderStatus] | None, Query()] = [OrderStatus.CLOSED],
    page: int = 0,
    quantity: int = 10,
    jwt: JWT = Depends(verify_jwt_http),
) -> PaginatedOrders:
    query = select(Orders).where(
        (Orders.user_id == jwt["sub"])
        & (Orders.market_type == market_type)
        & (Orders.instrument == instrument)
        & (Orders.status.in_(status))
    )

    if instrument is not None:
        query = query.where(Orders.instrument == instrument)

    if username is not None:
        if username != jwt["username"]:
            status = (OrderStatus.CLOSED,)

    async with DB_LOCK:
        async with get_db_session() as sess:
            res = await sess.execute(
                # select(Orders)
                # .where(
                #     (Orders.user_id == jwt["sub"])
                #     & (Orders.market_type == market_type)
                #     & (Orders.instrument == instrument)
                #     & (Orders.status.in_(status))
                # )
                query.offset(page * min(quantity, 50)).limit(quantity + 1)
            )

            orders = res.scalars().all()

    return PaginatedOrders(
        orders=[OrderRead(**vars(order)) for order in orders[:quantity]],
        has_next_page=len(orders) > quantity,
    )
