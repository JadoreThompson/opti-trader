from sqlalchemy import insert

from db_models import Orders
from utils.db import get_db_session
from ...config import FUTURES_QUEUE


async def enter_order(details: dict, user_id: str):
    details['standing_quantity'] = details['quantity']
    details['user_id'] = user_id
    
    async with get_db_session() as sess:
        res = await sess.execute(
            insert(Orders)
            .values(details)
            .returning(Orders)
        )
        res = res.scalar().first()
        await sess.commit()
    
    FUTURES_QUEUE.put_nowait({
        k: v 
        for k, v in vars(res).items() 
        if k != '_sa_instance_state'
    })
    