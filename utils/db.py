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
    sqlalc_uri = \
        db_url.format(quote(os.getenv('DB_PASSWORD')))\
            .replace('+asyncpg', '')
    
    sqlalc_uri = sqlalc_uri.replace('%', '%%')
    config = configparser.ConfigParser(interpolation=None)
    config.read('alembic.ini')

    config['alembic'].update({'sqlalchemy.url': sqlalc_uri})
    
    with open('alembic.ini', 'w') as f:
        config.write(f)    


def alembic_upgrade_head() -> None:
    from dotenv import load_dotenv
    load_dotenv()
    
    with open('alembic.ini', 'r') as f:
        alembic_ini = f.read()
        
    write_sqlalchemy_url(DB_URL)
    subprocess.run(['alembic', 'upgrade', 'head'])
    
    with open('alembic.ini', 'w') as f:
        f.write(alembic_ini)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[None, AsyncSession]:
    async with smaker() as session:
        yield session
