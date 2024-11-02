from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

# Local
# from config import DB_ENGINE
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
    # async with AsyncSession(DB_ENGINE) as session:
    async with async_session_maker() as session:
        try:
            yield session
            # await session.commit()
        except Exception as e:
            print("[GET DB SESSION][ERROR] >> ", type(e), str(e))
            await session.rollback()
            pass
        finally:
            print("-" * 20)
            print(session)
            print("-" * 20)
            await session.close()
