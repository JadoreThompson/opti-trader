import os
from dotenv import load_dotenv
from urllib.parse import quote
from argon2 import PasswordHasher

import redis
from sqlalchemy.ext.asyncio import create_async_engine


load_dotenv()

CACHE: dict[str, dict[str, any]] = {}

# Security
API_KEY_ALIAS = 'api-key'
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

PH = PasswordHasher(time_cost=2, memory_cost=102400, parallelism=8)


# Redis
REDIS_CONN_POOL = redis.asyncio.connection.ConnectionPool(max_connections=20)
REDIS_CLIENT = redis.asyncio.client.Redis(connection_pool=REDIS_CONN_POOL)


# DB
DB_URL = \
    f"postgresql+asyncpg://{os.getenv("DB_USER")}:{quote(os.getenv('DB_PASSWORD'))}\
@{os.getenv("DB_HOST")}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
DB_ENGINE = create_async_engine(DB_URL, pool_size=20)

TICKERS = ['BTC/USDT', 'SOL/USDT', 'ETH/USDT']
