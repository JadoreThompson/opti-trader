from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import AsyncSession

from config import ASYNC_DB_ENGINE, DB_ENGINE


smaker = sessionmaker(bind=ASYNC_DB_ENGINE, class_=AsyncSession, expire_on_commit=False)
smaker_sync = sessionmaker(bind=DB_ENGINE, class_=Session, expire_on_commit=False)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with smaker.begin() as session:
        yield session


@contextmanager
def get_db_session_sync() -> Generator[Session, None, None]:
    with smaker_sync() as sess:
        yield sess
