import configparser

from contextlib import asynccontextmanager, contextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker, Session
from typing import AsyncGenerator, Generator

from config import DB_ENGINE, DB_ENGINE_SYNC, DB_URL

smaker = sessionmaker(bind=DB_ENGINE, class_=AsyncSession, expire_on_commit=False)
smaker_sync = sessionmaker(bind=DB_ENGINE_SYNC, class_=Session, expire_on_commit=False)


def write_sqlalchemy_url() -> None:
    """Writes db url into the alamebic.ini file"""
    sqlalc_uri = DB_URL.replace("+asyncpg", "").replace("%", "%%")
    config = configparser.ConfigParser(interpolation=None)
    config.read("alembic.ini")

    config["alembic"].update({"sqlalchemy.url": sqlalc_uri})

    with open("alembic.ini", "w") as f:
        config.write(f)


def remove_sqlalchemy_url():
    """removes the db url into the alamebic.ini file"""
    config = configparser.ConfigParser(interpolation=None)
    config.read("alembic.ini")
    config["alembic"].update({"sqlalchemy.url": ""})

    with open("alembic.ini", "w") as f:
        config.write(f)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with smaker.begin() as session:
        yield session


@contextmanager
def get_db_session_sync() -> Generator[Session, None, None]:
    with smaker_sync() as sess:
        yield sess
