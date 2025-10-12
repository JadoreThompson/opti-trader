from utils.db import smaker_async


async def depends_db_session():
    async with smaker_async.begin() as sess:
        yield sess
