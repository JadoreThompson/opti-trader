import asyncio
import httpx
import multiprocessing
import uvicorn

from faker import Faker
from sqlalchemy import text
from config import REDIS_CLIENT
from r_mutex import Lock
from enums import MarketType, OrderType, Side
from utils.db import get_db_session, remove_sqlalchemy_url, write_sqlalchemy_url


fkr = Faker()
BASE_URL = "http://192.168.1.145:8000/api"


async def handle_run_server(queue: multiprocessing.Queue) -> None:
    from config import DB_LOCK
    from api import config as apiconfig

    apiconfig.FUTURES_QUEUE = queue
    fa_config = uvicorn.Config(
        "api.app:app",
        workers=3,
        host="0.0.0.0",
        port=8000,
        log_config=None,
    )
    fa_server = uvicorn.Server(fa_config)
    
    asyncio.create_task(DB_LOCK.run())
    await fa_server.serve()


def run_server(queue: multiprocessing.Queue) -> None:
    asyncio.run(handle_run_server(queue))


async def handle_engine(queue):
    from engine.futures import FuturesEngine
    from engine.pusher import Pusher
    
    order_lock = Lock(REDIS_CLIENT, 'orderlock', is_manager=False)
    instrument_lock = Lock(REDIS_CLIENT, 'instrumentlock')
    
    pusher = Pusher(order_lock)
    engine = FuturesEngine(order_lock, instrument_lock, pusher, queue)
    
    asyncio.create_task(order_lock.run())
    asyncio.create_task(instrument_lock.run())
    
    await engine.run()


def run_engine(queue: multiprocessing.Queue, ) -> None:
    asyncio.run(handle_engine(queue))


async def gen_fake_user(session) -> None:
    import json
    
    payload = {
        "username": fkr.first_name(),
        "email": fkr.email(),
        "password": fkr.word(),
    }
    
    print(json.dumps(payload, indent=4))
    
    await session.post(
        BASE_URL + "/auth/register",
        json=payload,
    )


async def gen_fake_orders(session, num_orders: int, cookie: str) -> None:
    import random
    randnum = lambda: round(random.random() * 100, 2)
    
    for _ in range(num_orders):
        await asyncio.sleep(0.1)
        order_type = random.choice([OrderType.LIMIT, OrderType.MARKET])
        payload = {
            "amount": random.randint(1, 5),
            "quantity": random.randint(1, 50),
            "instrument": "BTCUSD",
            "market_type": MarketType.FUTURES,
            "order_type": order_type,
            "side": random.choice([Side.BUY, Side.SELL]),
            "take_profit": random.choice([randnum(), None]),
            "stop_loss": random.choice([randnum(), None]),
        }

        if order_type == OrderType.LIMIT:
            payload["limit_price"] = randnum()

        await session.post(
            BASE_URL + "/order/",
            json=payload,
            cookies=cookie,
        )


async def load_db(num_users: int, num_orders: int) -> None:
    async def generate():
        async with httpx.AsyncClient() as sess:
            try:
                cookie = await gen_fake_user(sess)
                await gen_fake_orders(sess, num_orders, cookie)
            except Exception as e:
                print(f"[{load_db.__name__}]", type(e), str(e))

    for _ in range(0, num_users, 3):
        await asyncio.gather(*[generate() for _ in range(3)])


async def migrate():
    import subprocess
    from config import DEV_MODE, DB_URL

    write_sqlalchemy_url(DB_URL.replace("+asyncpg", ""))
    subprocess.run(["alembic", "upgrade", "head"], check=True)

    async with get_db_session() as sess:
        if DEV_MODE:
            await sess.execute(text("DELETE FROM orders;"))
            await sess.execute(text("DELETE FROM users;"))

        await sess.execute(text("SELECT COUNT(*) FROM orders;"))
        await sess.commit()


async def main(gen_fake: bool = False, num_users: int = 1, num_orders: int = 1) -> None:
    queue = multiprocessing.Queue()
    ps = [
        multiprocessing.Process(target=run_server, args=(queue,), name="server"),
        multiprocessing.Process(target=run_engine, args=(queue,), name="engine"),
    ]

    for p in ps:
        p.start()

    await asyncio.sleep(3)
    await migrate()
    
    if gen_fake:
        await load_db(num_users, num_orders)

    try:
        while True:
            for p in ps:
                if not p.is_alive():
                    raise Exception(f"{p.name} has died")
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
    asyncio.run(main(True, 1000, 1_000_000))
