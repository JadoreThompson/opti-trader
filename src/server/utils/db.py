from utils.db import smaker


async def depends_db_session():
    async with smaker.begin() as sess:
        yield sess
