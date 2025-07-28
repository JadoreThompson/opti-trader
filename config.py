import logging
import os

from celery import Celery
from datetime import timedelta
from dotenv import load_dotenv
from json import loads
from redis.asyncio import Redis
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from urllib.parse import quote


load_dotenv()

BASE_PATH = os.path.dirname(__file__)
PRODUCTION = False


# Celery
CELERY_BROKER = os.getenv("CELERY_BROKER")
CELERY = Celery(broker=CELERY_BROKER)


# DB
DB_URL = f"postgresql+asyncpg://{os.getenv("DB_USER")}:{quote(os.getenv("DB_PASSWORD"))}@{os.getenv("DB_HOST")}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
DB_ENGINE = create_async_engine(DB_URL)
DB_ENGINE_SYNC = create_engine(DB_URL.replace("+asyncpg", "+psycopg2"))
TEST_DB_URL = f"postgresql+asyncpg://{os.getenv("TEST_DB_USER")}:{quote(os.getenv("TEST_DB_PASSWORD"))}@{os.getenv("TEST_DB_HOST")}:{os.getenv('TEST_DB_PORT')}/{os.getenv('TEST_DB_NAME')}"
TEST_DB_ENGINE = create_engine(TEST_DB_URL.replace("+asyncpg", "+psycopg2"))
TEST_DB_ENGINE_ASYNC = create_async_engine(TEST_DB_URL)


# Redis
class CustomRedis(Redis):
    async def get(self, name: str):
        val = await super().get(name)
        if val is not None:
            return loads(val)
        return val


REDIS_CLIENT = CustomRedis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    password=os.getenv("REDIS_PASSWORD"),
    db=int(os.getenv("REDIS_DB", "0")),
    decode_responses=True,
)
FUTURES_QUEUE_KEY = os.getenv("FUTURES_QUEUE_KEY")
SPOT_QUEUE_KEY = os.getenv("SPOT_QUEUE_KEY")
ORDER_LOCK_PREFIX = os.getenv("ORDER_LOCK_PREFIX")
INSTRUMENT_LOCK_PREFIX = os.getenv("INSTRUMENT_LOCK_PREFIX")
PAYLOAD_PUSHER_QUEUE = os.getenv("PAYLOAD_PUSHER_QUEUE")


# Server Security
COOKIE_ALIAS = "cookie-order-matcher"
JWT_SECRET_KEY = os.getenv("JWT_SECRET", "my-secret")
JWT_ALGO = os.getenv("JWT_ALGO", "HS256")
JWT_EXPIRY = timedelta(days=1000)



# Logging
logging.basicConfig(
    level=logging.INFO,
    filename="app.log",
    filemode="w",
    format="%(asctime)s %(levelname)s: %(message)s",
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter("%(levelname)s: %(name)s - %(message)s"))
logging.getLogger().addHandler(console)


TEST_BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:80")