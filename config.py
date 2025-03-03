import argon2
import redis
import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from urllib.parse import quote

load_dotenv()

DEV_MODE = True

DB_URL = \
    f"postgresql+asyncpg://{os.getenv("DB_USER")}:{{}}@{os.getenv("DB_HOST")}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

# DB
DB_ENGINE = create_async_engine(
    DB_URL.format(quote(os.getenv('DB_PASSWORD'))),
    future=True, 
    echo_pool=True,
    pool_size=50,
    max_overflow=100,
    pool_timeout=30,
    pool_recycle=600,
)

REDIS_CLIENT = redis.asyncio.Redis(
    connection_pool=redis.asyncio.connection.ConnectionPool(
        connection_class=redis.asyncio.connection.Connection,
        max_connections=100,
    )
)

# Misc
PH = argon2.PasswordHasher(
    time_cost=2,
    memory_cost=1_024_000,
    parallelism=8,
)