import asyncio
import logging
import redis.asyncio
import redis.asyncio.connection
import argon2
import os
import redis
import sys

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from urllib.parse import quote

from engine.lock.lock import Lock

load_dotenv()

DEV_MODE = True
logger = logging.getLogger()
logging.basicConfig(
    filename=f"app.log",
    level=logging.INFO,
    format="[%(levelname)s][%(asctime)s] %(name)s - %(funcName)s - %(message)s",
)


def handle_exc(exc_type, exc_value, tcb):
    if not issubclass(exc_type, KeyboardInterrupt):
        logging.error("Uncaught Exc - ", exc_info=(exc_type, exc_value, tcb))

sys.excepthook = handle_exc


# Redis
REDIS_CLIENT = redis.asyncio.Redis(
    connection_pool=redis.asyncio.connection.ConnectionPool(
        connection_class=redis.asyncio.connection.Connection,
        max_connections=100,
    )
)
ORDER_UPDATE_CHANNEL = "order.updates"
BALANCE_UPDATE_CHANNEL = "balance.updates"


# DB
DB_URL = f"postgresql+asyncpg://{os.getenv("DB_USER")}:{{}}@{os.getenv("DB_HOST")}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
DB_ENGINE = create_async_engine(
    DB_URL.format(quote(os.getenv("DB_PASSWORD"))),
    future=True,
    echo_pool=True,
    pool_size=1000,
    max_overflow=100,
    pool_timeout=30,
    pool_recycle=600,
)
print("Calling db lock")
DB_LOCK = Lock(REDIS_CLIENT, 'test')


# Misc
PH = argon2.PasswordHasher(
    time_cost=2,
    memory_cost=1_024_000,
    parallelism=8,
)
