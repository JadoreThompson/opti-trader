from contextlib import asynccontextmanager

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


async def get_orders(constraints: dict) -> list[dict]:
    """
    Returns all orders withhin a DB that follow the constraints

    Args:
        constraints (dict)
    """ 
    query = select(Orders).where(Orders.user_id == constraints['user_id'])
    constraints = {k: v for k, v in constraints.items() if v and k != 'user_id'}
    
    if constraints.get('order_status', None):
        query = query.where(Orders.order_status == constraints['order_status'])
        
    async with get_db_session() as session:
        results = await session.execute(query)
        return [vars(order) for order in results.scalars()]


async def get_active_orders(user_id: str) -> list[dict]:
    """
    Returns all orders withhin a DB that follow the constraints

    Args:
        constraints (dict)
    """ 
    async with get_db_session() as session:
        results = await session.execute(
            select(Orders).where(
                (Orders.user_id == user_id)
                & (Orders.order_status != OrderStatus.CLOSED)
            )
        )
        return [
            {
                k: v 
                for k, v in vars(order).items() if k != '_sa_instance_state'    
            } 
            for order in results.scalars().all()
        ]
