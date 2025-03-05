import redis.asyncio
import redis.asyncio.connection
import argon2
import asyncio
import os
import redis

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from urllib.parse import quote

load_dotenv()

DEV_MODE = True

DB_URL = f"postgresql+asyncpg://{os.getenv("DB_USER")}:{{}}@{os.getenv("DB_HOST")}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

# DB
DB_ENGINE = create_async_engine(
    DB_URL.format(quote(os.getenv("DB_PASSWORD"))),
    future=True,
    echo_pool=True,
    pool_size=1000,
    max_overflow=100,
    pool_timeout=30,
    pool_recycle=600,
)
DB_LOCK = None

# Redis
REDIS_CLIENT = redis.asyncio.Redis(
    connection_pool=redis.asyncio.connection.ConnectionPool(
        connection_class=redis.asyncio.connection.Connection,
        max_connections=100,
    )
)
# REDIS_LOCK_MANAGER = Aioredlock([{"host": "localhost", "port": 6379, "db": 0}])
ORDER_UPDATE_CHANNEL = "order.updates"
BALANCE_UPDATE_CHANNEL = "balance.updates"

# Misc
PH = argon2.PasswordHasher(
    time_cost=2,
    memory_cost=1_024_000,
    parallelism=8,
)
