import asyncio
import multiprocessing
import subprocess
import uvicorn

from sqlalchemy import text
from r_mutex import Lock
from api import config as apiconfig
from engine.futures_engine import FuturesEngine
from engine.pusher import Pusher
from config import (
    INSTRUMENT_LOCK_PREFIX,
    ORDER_LOCK_PREFIX,
    REDIS_CLIENT,
    DB_LOCK,
    DEV_MODE,
    DB_URL
)
from utils.db import get_db_session, remove_sqlalchemy_url, write_sqlalchemy_url


async def handle_run_server(queue: multiprocessing.Queue) -> None:
    """Handles uvicorn config and run
    Args:
        queue (multiprocessing.Queue): Queue used to ingest orders into the engine
    """
    apiconfig.FUTURES_QUEUE = queue
    fa_config = uvicorn.Config(
        "api.app:app",
        workers=3,
        host="0.0.0.0",
        port=8000,
        # log_config=None,
    )
    fa_server = uvicorn.Server(fa_config)

    asyncio.create_task(DB_LOCK.run())
    await fa_server.serve()


def run_server(queue: multiprocessing.Queue) -> None:
    """Server entrypoint
    
    Args:
        queue (multiprocessing.Queue): Queue used to ingest orders into the engine
    """
    asyncio.run(handle_run_server(queue))


async def handle_run_engine(queue: multiprocessing.Queue) -> None:
    """Handles configs for engine and running it
    Args:
        queue (multiprocessing.Queue): Queue used to ingest orders into the engine
    """
    order_lock = Lock(REDIS_CLIENT, ORDER_LOCK_PREFIX, is_manager=False)
    instrument_lock = Lock(REDIS_CLIENT, INSTRUMENT_LOCK_PREFIX)

    pusher = Pusher(order_lock)
    engine = FuturesEngine(order_lock, instrument_lock, pusher, queue)

    asyncio.create_task(order_lock.run())
    asyncio.create_task(instrument_lock.run())

    await engine.run()


def run_engine(
    queue: multiprocessing.Queue,
) -> None:
    """Engine Entrypoint

    Args:
        queue (multiprocessing.Queue): Queue used to ingest orders into the engine
    """    
    asyncio.run(handle_run_engine(queue))


async def migrate() -> None:
    """Runs alembic commands. To be run before before running server"""
    write_sqlalchemy_url(DB_URL.replace("+asyncpg", ""))
    subprocess.run(["alembic", "upgrade", "head"], check=True)

    async with get_db_session() as sess:
        if DEV_MODE:
            await sess.execute(text("DELETE FROM orders;"))
            await sess.execute(text("DELETE FROM users;"))

        await sess.execute(text("SELECT COUNT(*) FROM orders;"))
        await sess.commit()


async def main() -> None:
    """Main Entrypoint
    Creates and manages seperate processes for server and engine
    """
    queue = multiprocessing.Queue()

    ps = [
        multiprocessing.Process(target=run_server, args=(queue,), name="server"),
        multiprocessing.Process(target=run_engine, args=(queue,), name="engine"),
    ]

    for p in ps:
        p.start()

    await migrate()

    try:
        while True:
            for p in ps:
                if not p.is_alive():
                    raise KeyboardInterrupt(f"{p.name} has died")
            await asyncio.sleep(2)
    except Exception as e:
        remove_sqlalchemy_url()
        print("[pm][Error] => ", str(e))
        print("Terminating processes")
        for p in ps:
            p.terminate()
            p.join()
            print(f"Terminated {p.name}")
        raise e


if __name__ == "__main__":
    asyncio.run(main())
