import os
from urllib.parse import quote

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, Session


BASE_PATH = os.path.dirname(__file__)


load_dotenv(os.path.join(BASE_PATH, ".env"), override=True)


DB_USER_CREDS = f"{os.getenv("DB_USERNAME")}:{quote(os.getenv("DB_PASSWORD"))}"
DB_HOST_CREDS = f"{os.getenv("DB_HOST")}:{quote(os.getenv("DB_PORT"))}"
DB_NAME = os.getenv("DB_NAME")
DB_URL = f"postgresql+psycopg2://{DB_USER_CREDS}@{DB_HOST_CREDS}/{DB_NAME}"
ASYNC_DB_URL = f"postgresql+asyncpg://{DB_USER_CREDS}@{DB_HOST_CREDS}/{DB_NAME}"


engine = create_engine(DB_URL)
smaker = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

engine_async = create_async_engine(ASYNC_DB_URL)
smaker_async = sessionmaker(
    bind=engine_async, class_=AsyncSession, expire_on_commit=False
)
