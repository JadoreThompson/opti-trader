from json import loads
import bcrypt
import os

from celery import Celery
from datetime import timedelta
from dotenv import load_dotenv
from redis.asyncio import Redis
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from urllib.parse import quote
from r_mutex import LockClient


class CustomRedis(Redis):
    async def get(self, name: str):
        val = await super().get(name)
        if val is not None:
            return loads(val)
        return val


load_dotenv()

BASE_PATH = os.getcwd()
PRODUCTION = False


# DB
DB_URL = f"postgresql+asyncpg://{os.getenv("DB_USER")}:{quote(os.getenv("DB_PASSWORD"))}@{os.getenv("DB_HOST")}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
DB_ENGINE = create_async_engine(DB_URL)
DB_ENGINE_SYNC = create_engine(DB_URL.replace("+asyncpg", "+psycopg2"))


CELERY_BROKER = os.getenv("CELERY_BROKER")
CELERY = Celery(broker=CELERY_BROKER)

# Redis
REDIS = CustomRedis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    password=os.getenv("REDIS_PASSWORD"),
    db=int(os.getenv("REDIS_DB", "0")),
    decode_responses=True,
)
ORDER_UPDATE_CHANNEL = os.getenv("ORDER_UPDATE_CHANNEL")
BALANCE_UPDATE_CHANNEL = os.getenv("BALANCE_UPDATE_CHANNEL")
FUTURES_QUEUE_KEY = os.getenv("FUTURES_QUEUE_KEY")
SPOT_QUEUE_KEY = os.getenv("SPOT_QUEUE_KEY")
ORDER_LOCK_PREFIX = os.getenv("ORDER_LOCK_PREFIX")
INSTRUMENT_LOCK_PREFIX = os.getenv("INSTRUMENT_LOCK_PREFIX")

# Server Security
COOKIE_ALIAS = "cookie-order-matcher"
JWT_SECRET_KEY = os.getenv("JWT_SECRET")
JWT_ALGO = os.getenv("JWT_ALGO")
JWT_EXPIRY = timedelta(days=1000)

