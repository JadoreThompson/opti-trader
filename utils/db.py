from contextlib import asynccontextmanager
from uuid import UUID
import asyncio

# SA
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

# Local
from enums import OrderStatus
from exceptions import DoesNotExist
from db_models import Orders
from tests.test_config import DB_ENGINE


async_session_maker = sessionmaker(
    DB_ENGINE,
    class_=AsyncSession,
    expire_on_commit=False
)


@asynccontextmanager
async def get_db_session():
    """
    Provides an asynchronous database session.

    Yields:
        AsyncSession: The database session for executing queries.
    Raises:
        Exception: If an error occurs during the session.
    """
    async with async_session_maker() as session:
        try:
            yield session
        
        except DoesNotExist:
            raise
        
        except Exception as e:
            print('Get DB Session Error: ', type(e), str(e))
            print("-" * 10)
            await session.rollback()
            pass
        
        finally:
            await session.close()

def constraints_to_tuple(constraints: dict) -> tuple:
    return tuple(sorted(constraints.items()))


_CACHE = {}

async def delete_from_internal_cache(user_id: str | UUID, channel: str | list, **kwargs) -> None:
    try:    
        if isinstance(channel, list):
            for c in channel:
                _CACHE[user_id].pop(c, None)
        else:
            _CACHE[user_id].pop(channel, None)
    except KeyError:
        pass
    
    
async def add_to_internal_cache(user_id: str | UUID, channel: str, value: any) -> None:
    _CACHE.setdefault(user_id, {})    
    _CACHE[user_id][channel] = value
    

async def retrieve_from_internal_cache(user_id: str | UUID, channel: str) -> any:
    try:
        return _CACHE[user_id][channel]
    except KeyError:
        return None


async def get_orders(user_id: str | UUID, **kwargs) -> list[dict]:
    """
    Returns all orders withhin a DB that follow the constraints

    Args:
        constraints (dict)
    """ 
    key = kwargs.get('order_status', None) or 'all'
    existing_data = await retrieve_from_internal_cache(user_id, 'orders')
    if existing_data:
        if key in existing_data:
            return existing_data[key]
    
    query = select(Orders).where(Orders.user_id == user_id)
    constraints = kwargs
        
    if constraints.get('order_status', None) != None:
        query = query.where(Orders.order_status == constraints['order_status'])
        
    async with get_db_session() as session:
        results = await session.execute(query.limit(1000))
    
    order_list = [vars(order) for order in results.scalars().all()]
    asyncio.create_task(add_to_internal_cache(user_id, 'orders', {key: order_list}))
    return order_list


async def get_active_orders(user_id: str) -> list[dict]:
    """
    Returns all orders withhin a DB that follow the constraints

    Args:
        constraints (dict)
    """
    existing_data = await retrieve_from_internal_cache(user_id, 'active_orders')
    if existing_data:
        return existing_data
    
    async with get_db_session() as session:
        results = await session.execute(
            select(Orders).where(
                (Orders.user_id == user_id)
                & (Orders.order_status != OrderStatus.CLOSED)
            )
        )
        
        existing_data = [
            {
                k: v 
                for k, v in vars(order).items() if k != '_sa_instance_state'    
            } 
            for order in results.scalars().all()
        ]
        
        asyncio.create_task(add_to_internal_cache(user_id, 'active_orders', existing_data))
        
        return existing_data
