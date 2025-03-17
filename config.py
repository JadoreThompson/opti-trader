import os
import logging
import sys

import argon2
import redis
import redis.asyncio
import redis.asyncio.connection

from dotenv import load_dotenv
from r_mutex import LockClient
from urllib.parse import quote
from sqlalchemy.ext.asyncio import create_async_engine


load_dotenv()

BASE_PATH = os.getcwd()
DEV_MODE = False

logger = logging.getLogger()
logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="[%(levelname)s][%(asctime)s] %(name)s - %(funcName)s - %(message)s",
)

def handle_exc(exc_type, exc_value, tcb):
    """Global Exception Handler"""
    if not issubclass(exc_type, KeyboardInterrupt):
        logging.error("Uncaught Exc - ", exc_info=(exc_type, exc_value, tcb))
        print(exc_type, exc_value)
        
sys.excepthook = handle_exc


# DB
DB_URL = f"postgresql+asyncpg://{os.getenv("DB_USER")}:{{}}@{os.getenv("DB_HOST")}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
DB_ENGINE = create_async_engine(
    DB_URL.format(quote(os.getenv("DB_PASSWORD"))),
    future=True,
    echo_pool=True,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=6000,
)


# Redis
REDIS_CLIENT = redis.asyncio.Redis(
    connection_pool=redis.asyncio.connection.ConnectionPool(
        connection_class=redis.asyncio.connection.Connection,
        max_connections=100,
    )
)
ORDER_UPDATE_CHANNEL = os.getenv("ORDER_UPDATE_CHANNEL")
BALANCE_UPDATE_CHANNEL = os.getenv("BALANCE_UPDATE_CHANNEL")
FUTURES_QUEUE_KEY = os.getenv("FUTURES_QUEUE_KEY")
SPOT_QUEUE_KEY = os.getenv("SPOT_QUEUE_KEY")
ORDER_LOCK_PREFIX = os.getenv("ORDER_LOCK_PREFIX")
INSTRUMENT_LOCK_PREFIX = os.getenv("INSTRUMENT_LOCK_PREFIX")


### 
PH = argon2.PasswordHasher(
    time_cost=int(os.getenv("TIME_COST")),
    memory_cost=int(os.getenv("MEMORY_COST")),
    parallelism=int(os.getenv("PARALLELISM")),
)

DB_LOCK = LockClient(REDIS_CLIENT, ORDER_LOCK_PREFIX, is_manager=False)