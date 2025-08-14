import os
from multiprocessing.queues import Queue as MPQueue
from urllib.parse import quote

from dotenv import load_dotenv
from redis import Redis
from redis.asyncio import Redis as RedisAsync
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine


PRODUCTION = False
BASE_PATH = os.path.dirname(__file__)


load_dotenv(os.path.join(BASE_PATH, ".env"))


# DB
DB_USER_CREDS = f"{os.getenv("DB_USERNAME")}:{quote(os.getenv("DB_PASSWORD"))}"
DB_HOST_CREDS = f"{os.getenv("DB_HOST")}:{quote(os.getenv("DB_PORT"))}"
DB_NAME = os.getenv("DB_NAME")
DB_URL = f"postgresql+psycopg2://{DB_USER_CREDS}@{DB_HOST_CREDS}/{DB_NAME}"
ASYNC_DB_URL = f"postgresql+asyncpg://{DB_USER_CREDS}@{DB_HOST_CREDS}/{DB_NAME}"
DB_ENGINE = create_engine(DB_URL)
ASYNC_DB_ENGINE = create_async_engine(ASYNC_DB_URL)


# Redis
redis_kwargs = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", "6379")),
    "password": os.getenv("REDIS_PASSWORD"),
    "db": int(os.getenv("REDIS_DB", "0")),
}
REDIS_CLIENT_ASYNC = RedisAsync(**redis_kwargs)
REDIS_CLIENT = Redis(**redis_kwargs)

INSTRUMENT_PRICE_QUEUE = os.getenv("INSTRUMENT_PRICE_QUEUE", "channel-1")
ORDER_UPDATE_QUEUE = os.getenv("ORDER_UPDATE_QUEUE", "channel-2")
CASH_BALANCE_HKEY = os.getenv("CASH_BALANCE_HKEY", "channel-3")
CASH_ESCROW_HKEY = os.getenv("CASH_ESCROW_HKEY", "channel-4")


# Auth
COOKIE_ALIAS = "opti-trader-cookie"
JWT_SECRET_KEY = os.getenv("JWT_SECRET", "my-secret")
JWT_ALGO = os.getenv("JWT_ALGO", "HS256")
JWT_EXPIRY_MINS = int(os.getenv("JWT_EXPIRY_MINS", "10_000"))


PAGE_SIZE = 10


# Engine
COMMAND_QUEUE: MPQueue | None = None
