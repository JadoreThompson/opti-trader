from contextlib import asynccontextmanager
from collections import defaultdict
from uuid import UUID
import asyncio

# SA
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

# Local
from config import DB_ENGINE
from enums import OrderStatus
from exceptions import DoesNotExist, InvalidAction
from db_models import Orders, Users



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
            await session.rollback()
            raise e
        finally:
            await session.close()
            

def constraints_to_tuple(constraints: dict) -> tuple:
    return tuple(sorted(constraints.items()))


_CACHE = {}

def delete_from_internal_cache(user_id: str | UUID, channel: str | list, **kwargs) -> None:
    global _CACHE
    try:    
        if isinstance(channel, list):
            for item in channel:
                _CACHE[user_id].pop(item, None)
        else:
            _CACHE[user_id].pop(channel, None)
    except KeyError:
        pass
    except Exception as e:
        print('cache ', type(e), str(e))
    
    
def add_to_internal_cache(user_id: str | UUID, channel: str, value: any) -> None:
    global _CACHE
    _CACHE.setdefault(user_id, {})  
    
    if channel not in _CACHE[user_id]:
       _CACHE[user_id][channel] = {}
    
    if isinstance(value, dict):
        _CACHE[user_id][channel].update(value)
    else:
        _CACHE[user_id][channel] = value
    
    

def retrieve_from_internal_cache(user_id: str | UUID, channel: str) -> any:
    global _CACHE
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
    existing_data = retrieve_from_internal_cache(user_id, 'orders')
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
    add_to_internal_cache(user_id, 'orders', {key: order_list})
    return order_list


async def get_active_orders(user_id: str) -> list[dict]:
    """
    Returns all orders withhin a DB that follow the constraints

    Args:
        constraints (dict)
    """
    existing_data = retrieve_from_internal_cache(user_id, 'active_orders')
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
        
        add_to_internal_cache(user_id, 'active_orders', existing_data)
        return existing_data


async def check_user_exists(user_id: str):
    try:
        async with get_db_session() as session:
            result = await session.execute(
                select(Users)
                .where(Users.user_id == user_id)
            )
            user = result.scalar()
                
            if not user:
                return InvalidAction("Invalid user")
            return user            
    except Exception:
        raise


async def check_visible_user(username: str) -> str:
    """
    Returns the user_id for the username passsed in param
    if the user exists and has visible set to True.
    
    Args:
        username (str):

    Returns:
        str: UserId
    """    
    async with get_db_session() as session:
        res = await session.execute(
            select(Users.user_id)
            .where(
                (Users.username == username) &
                (Users.visible == True)
            )
        )
        return res.first()[0]
        
