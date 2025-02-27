import argon2
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from urllib.parse import quote

load_dotenv()

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

# Misc
PH = argon2.PasswordHasher(
    time_cost=2,
    memory_cost=1_024_000,
    parallelism=8,
)