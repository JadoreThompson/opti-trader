from email.policy import HTTP
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from config import DB_LOCK
from enums import OrderStatus


from ..order.models import OrderRead
from db_models import Orders, Users
from utils.db import get_db_session
from .model import Profile
from ...middleware import JWT, verify_cookie_http

account = APIRouter(prefix="/account", tags=["account"])


@account.get("/")
async def get_account(jwt: JWT = Depends(verify_cookie_http)) -> Profile:
    async with DB_LOCK:
        print("[/account/] I've got the lock")
        async with get_db_session() as sess:
            res = await sess.execute(select(Users).where(Users.user_id == jwt["sub"]))
            user = res.scalar()

    if not user:
        raise HTTPException(status_code=404, detail="User doesn't exist")

    return Profile(**vars(user))


@account.get("/orders")
async def get_orders(jwt: JWT = Depends(verify_cookie_http)) -> list[OrderRead]:
    async with DB_LOCK:
        # print("[/orders] I've got the lock")
        async with get_db_session() as sess:
            res = await sess.execute(select(Orders).where(Orders.user_id == jwt["sub"]))
    return [OrderRead(**vars(order)) for order in res.scalars().all()]
