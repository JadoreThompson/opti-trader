import asyncio
from celery import Celery


app = Celery(broker='redis://localhost:6379/0')
app.conf.result_backend = None


@app.task
def main():
    asyncio.run(test())


async def test():
    await asyncio.sleep(5)
