from contextlib import asynccontextmanager
from tests.config import smaker_async


@asynccontextmanager
async def async_db_session_context():
    async with smaker_async.begin() as sess:
        yield sess
