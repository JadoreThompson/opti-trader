import asyncio
import json
import logging
import redis
from sqlalchemy import update

from config import ASYNC_REDIS_CONN_POOL, REDIS_HOST
from db_models import DBOrder
from utils.auth import get_db_session


logger = logging.getLogger(__name__)
REDIS = redis.asyncio.client.Redis(
    connection_pool=ASYNC_REDIS_CONN_POOL, 
    host=REDIS_HOST
)

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
                await session.execute(update(DBOrder),[order])
                await session.commit()
            except Exception as e:
                await session.rollback()
            finally:
                await asyncio.sleep(0.1)
                
                
async def publish_update_to_client(channel: str, message: str | dict) -> None:
        """
        Publishes message to Redis channel

        Args:
            channel (str):
            message (str): 
        """        
        try:
            if isinstance(message, dict):
                message = json.dumps(message)
            
            if isinstance(message, str):
                await REDIS.publish(channel=channel, message=message)
        except Exception as e:
            logger.error(str(e))
