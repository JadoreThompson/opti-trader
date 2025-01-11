import asyncio
import datetime
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
                if isinstance(order['created_at'], str):
                    order['created_at'] = datetime.datetime.strptime(order['created_at'], "%Y-%m-%d %H:%M:%S.%f")
                    
                await session.execute(
                    update(DBOrder),
                    [
                        {
                            k: v 
                            for k, v in order.items() 
                            if k != 'type'
                        }
                    ]
                )
                await session.commit()
            except Exception as e:
                await session.rollback()

            await asyncio.sleep(0.001)
                
                
async def publish_update_to_client(channel: str, message: str | dict) -> None:
        """
        Publishes message to Redis channel

        Args:
            channel (str):
            message (str): 
        """        
        try:
            if isinstance(message, dict):
                print(json.dumps(message, indent=4))
                message = json.dumps(message)
            
            if isinstance(message, str):                
                await REDIS.publish(channel=channel, message=message)
        except Exception as e:
            logger.error(str(e))
