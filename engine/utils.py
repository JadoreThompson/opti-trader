import asyncio
from sqlalchemy import update
from db_models import Orders
from utils.auth import get_db_session


async def batch_update(orders: list[dict]) -> None:
    """
    Performs batch update in the Orders Table
    
    Args:
        orders (list[dict]).
    """        
    # During testing a DBAPIError is thrown since the orders
    # are only generated in memory and not in DB
    async with get_db_session() as session:
        for order in orders:
            try:
                order.pop('type', None)
                await session.execute(update(Orders),[order])
                await session.commit()
            except Exception as e:
                await session.rollback()
            finally:
                await asyncio.sleep(0.1)
                