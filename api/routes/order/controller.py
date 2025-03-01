from sqlalchemy import insert

from db_models import Orders
from enums import Side
from utils.db import get_db_session
from .models import OrderWrite
from ...config import FUTURES_QUEUE


def validate_order(price: float, order: OrderWrite) -> bool:
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


async def enter_order(details: dict, user_id: str):
    details['standing_quantity'] = details['quantity']
    details['user_id'] = user_id
    
    async with get_db_session() as sess:
        res = await sess.execute(
            insert(Orders)
            .values(details)
            .returning(Orders)
        )
        order = res.scalar()
        await sess.commit()
    
    FUTURES_QUEUE.put_nowait({
        k: v 
        for k, v in vars(order).items() 
        if k != '_sa_instance_state'
    })
    