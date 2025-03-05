from sqlalchemy import insert, select, update

from config import DB_LOCK
from db_models import Orders, Users
from enums import MarketType, Side
from utils.db import get_db_session
from .models import OrderWrite
from ...config import FUTURES_QUEUE


def validate_order_details(price: float, order: OrderWrite) -> bool:
    if order.side == Side.SELL:
        if order.limit_price:
            if order.limit_price <= price:
                raise ValueError("Limit price must be greater than market price")
        if order.take_profit:
            if order.take_profit >= price:
                raise ValueError("TP must be less than market price")
        if order.stop_loss:
            if order.stop_loss <= price:
                raise ValueError("SL must be greater than market price")

    if order.side == Side.BUY:
        if order.limit_price:
            if order.limit_price >= price:
                raise ValueError("Limit price must be less than market price")
        if order.take_profit:
            if order.take_profit <= price:
                raise ValueError("TP must be greater than market price")
        if order.stop_loss:
            if order.stop_loss >= price:
                raise ValueError("SL must be less than market price")

    return True


async def enter_order(details: dict, user_id: str) -> None:
    details["standing_quantity"] = details["quantity"]
    details["user_id"] = user_id

    async with DB_LOCK:        
        # print("[enter_order] I've got the lock now")
        async with get_db_session() as sess:
            res = await sess.execute(select(Users.balance).where(Users.user_id == user_id))
            
            balance = res.first()[0] - (details["amount"] * details["quantity"])
            if balance < 0:
                raise ValueError("Insufficient balance")

            await sess.execute(update(Users).values(balance=balance))
            res = await sess.execute(insert(Orders).values(details).returning(Orders))
            order = res.scalar()
            await sess.commit()

    if details["market_type"] == MarketType.FUTURES:
        payload = vars(order)
        del payload['_sa_instance_state']
        print('put payload:', payload)
        FUTURES_QUEUE.put_nowait(payload)
