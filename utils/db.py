import configparser
import os
import subprocess

from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from typing import AsyncGenerator
from urllib.parse import quote

from config import DB_ENGINE, DB_URL

smaker = sessionmaker(
    bind=DB_ENGINE, 
    class_=AsyncSession, 
    expire_on_commit=False
)

def write_sqlalchemy_url(db_url: str) -> None:
    """Writes db url into the alamebic.ini file"""
    
    sqlalc_uri = \
        db_url.format(quote(os.getenv('DB_PASSWORD')))\
            .replace('+asyncpg', '')
    
    sqlalc_uri = sqlalc_uri.replace('%', '%%')
    config = configparser.ConfigParser(interpolation=None)
    config.read('alembic.ini')

    config['alembic'].update({'sqlalchemy.url': sqlalc_uri})
    
    with open('alembic.ini', 'w') as f:
        config.write(f)    


def remove_sqlalchemy_url():
    """removes the db url into the alamebic.ini file"""
    config = configparser.ConfigParser(interpolation=None)
    config.read('alembic.ini')
    config['alembic'].update({'sqlalchemy.url': ''})
    
    with open('alembic.ini', 'w') as f:
        config.write(f)    


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[None, AsyncSession]:
    async with smaker.begin() as session:
        yield session
