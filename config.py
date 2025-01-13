import redis
import logging
import uuid

import os
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import quote
from argon2 import PasswordHasher
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import create_async_engine

from mailers.gmailer import GMailer
from utils.connection import AsyncRedisConnection, SyncRedisConnection

load_dotenv(override=False)
ROOT = Path().absolute()

# Security
API_KEY_ALIAS = 'api-key'
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
PH = PasswordHasher(time_cost=2, memory_cost=102400, parallelism=8)

# Redis
REDIS_HOST = os.getenv('REDIS_HOST')
SYNC_REDIS_CONN_POOL = redis.connection.ConnectionPool(
    connection_class=SyncRedisConnection,
    max_connections=20
)
ASYNC_REDIS_CONN_POOL = redis.asyncio.connection.ConnectionPool(
    connection_class=AsyncRedisConnection,
    max_connections=20
)

# DB
DB_URL = \
    f"postgresql+asyncpg://{os.getenv("DB_USER")}:{{}}\
@{os.getenv("DB_HOST")}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
DB_ENGINE = create_async_engine(
    DB_URL.format(quote(os.getenv('DB_PASSWORD'))),
    future=True, 
    pool_size=10, 
    max_overflow=10, 
    echo_pool=True
)
TICKERS = ['BTC/USDT', 'SOL/USDT', 'ETH/USDT']

from alembic.config import Config
alconfig = Config(ROOT.joinpath('\\alembic.ini'))
alconfig.set_main_option(
    'sqlalchemy.url', 
    DB_URL.format(os.getenv('DB_PASSWORD')).replace('+asyncpg', '')
)

# Logging
LOG_FOLDER = os.getcwd() + '/log'
if not os.path.exists(LOG_FOLDER):
    os.mkdir(LOG_FOLDER)
    
logging.basicConfig(
    filename=LOG_FOLDER + f"/app.log", 
    level=logging.INFO, 
    format="[%(levelname)s][%(asctime)s] %(name)s - %(funcName)s - %(message)s"
)

# Mailer
MAILER = GMailer()
MAILER.create_service(
    ['https://mail.google.com/'],
    './client_secret.json',    
)