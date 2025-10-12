from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker, Session

from config import ASYNC_DB_ENGINE, DB_ENGINE


smaker_async = sessionmaker(
    bind=ASYNC_DB_ENGINE, class_=AsyncSession, expire_on_commit=False
)
smaker = sessionmaker(bind=DB_ENGINE, class_=Session, expire_on_commit=False)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with smaker_async.begin() as session:
        try:
            yield session
        except:
            await session.rollback()
            raise


@contextmanager
def get_db_session_sync() -> Generator[Session, None, None]:
    with smaker() as sess:
        yield sess
