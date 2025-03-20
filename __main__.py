import asyncio
import multiprocessing
import os
import subprocess
from urllib.parse import quote
import uvicorn

from r_mutex import LockClient, LockManager
from sqlalchemy import select, text
from typing import List, Type

from config import (
    INSTRUMENT_LOCK_PREFIX,
    ORDER_LOCK_PREFIX,
    REDIS_CLIENT,
    DB_LOCK,
    DEV_MODE,
    DB_URL,
)
from db_models import Instruments
from api.routes.instrument.utils import cache_market_data
from engine.base_engine import BaseEngine
from engine.futures_engine import FuturesEngine
from engine.pusher import Pusher
from engine.spot_engine import SpotEngine
from utils.db import get_db_session, remove_sqlalchemy_url, write_sqlalchemy_url


async def fetch_instruments() -> list[str]:
    async with get_db_session() as sess:
        res = await sess.execute(select(Instruments.instrument))
        res = res.all()
    return [item[0] for item in res]


async def handle_run_server() -> None:
    """
    Handles uvicorn config and run
    """
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


def run_server() -> None:
    """Server entrypoint"""
    asyncio.run(handle_run_server())


async def handle_run_engine(engine_class: Type[BaseEngine]) -> None:
    order_lock = LockClient(REDIS_CLIENT, ORDER_LOCK_PREFIX, is_manager=False)
    instrument_lock = LockClient(REDIS_CLIENT, INSTRUMENT_LOCK_PREFIX, is_manager=False)

    pusher = Pusher(order_lock)
    asyncio.create_task(order_lock.run())
    asyncio.create_task(instrument_lock.run())

    engine = engine_class(instrument_lock, pusher)
    await engine.run(await fetch_instruments())


def run_engine(engine_class):
    asyncio.run(handle_run_engine(engine_class))


async def listen_for_instruments(instruments: List[str], lock: asyncio.Lock) -> None:
    async with REDIS_CLIENT.pubsub() as ps:
        await ps.subscribe("instrument.new")
        async for message in ps.listen():
            if message["type"] == "subscribe":
                continue

            async with lock:
                instruments.append(message["data"])


async def handle_market_data_cache() -> None:
    lock = asyncio.Lock()
    instruments = await fetch_instruments()
    sleep = 60 * 60 * 2  # seconds
    asyncio.create_task(listen_for_instruments(instruments, lock))

    while True:
        async with lock:
            for instrument in instruments:
                await cache_market_data(instrument)
        await asyncio.sleep(sleep)


def run_market_data_cache() -> None:
    asyncio.run(handle_market_data_cache())


async def run_migrate() -> None:
    """Runs alembic commands. To be run before before running server"""
    write_sqlalchemy_url(DB_URL.format(quote(os.getenv("DB_PASSWORD"))))
    subprocess.run(["alembic", "upgrade", "head"], check=True)

    async with get_db_session() as sess:
        if DEV_MODE:
            await sess.execute(text("DELETE FROM orders;"))
            await sess.execute(text("DELETE FROM users WHERE username != 'admin';"))

        await sess.execute(text("SELECT COUNT(*) FROM orders;"))
        await sess.commit()


async def main() -> None:
    """
    Main Entrypoint
    Creates and manages seperate processes for server and engine
    """

    instrument_lock_task = asyncio.create_task(
        LockManager(REDIS_CLIENT, INSTRUMENT_LOCK_PREFIX).run()
    )
    order_lock_task = asyncio.create_task(
        LockManager(REDIS_CLIENT, ORDER_LOCK_PREFIX).run()
    )
    await run_migrate()

    ps_kwargs: list[dict] = [
        {"target": run_server, "name": "server"},
        {"target": run_engine, "args": (FuturesEngine,), "name": "futures engine"},
        {"target": run_engine, "args": (SpotEngine,), "name": "spot engine"},
        {"target": run_market_data_cache, "name": "market data cache"},
    ]

    ps: list[multiprocessing.Process] = [
        multiprocessing.Process(**kwargs) for kwargs in ps_kwargs
    ]

    for p in ps:
        p.start()

    try:
        print("[pm] Initialising managing process")
        while True:
            for ind, p in enumerate(ps.copy()):
                if not p.is_alive():
                    print(f"{p.name} has died")
                    ps.remove(p)

                    new_p = multiprocessing.Process(**ps_kwargs[ind])
                    ps.insert(ind, new_p)

                    new_p.start()
                    print(f"{new_p.name} has been restarted")

            await asyncio.sleep(2)
    except Exception as e:
        print("[pm][Error] => ", type(e), str(e))
        print("Terminating processes")

        for p in ps:
            p.join()
            p.terminate()
            print(f"Terminated {p.name}")

        order_lock_task.cancel()
        instrument_lock_task.cancel()
    finally:
        remove_sqlalchemy_url()


if __name__ == "__main__":
    asyncio.run(main())
