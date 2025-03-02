import asyncio
import random
import httpx
import multiprocessing
import uvicorn

from sqlalchemy import text
from enums import OrderType, Side
from utils.db import get_db_session

BASE_URL = "http://192.168.1.145:8000/api"

def run_server(queue: multiprocessing.Queue) -> None:
    from api import config
    config.FUTURES_QUEUE = queue
    
    uvicorn.run(
        "api.app:app", 
        host="0.0.0.0", 
        port=8000, 
        # reload=True
        log_config=None,
    )


def run_engine(queue: multiprocessing.Queue) -> None:
    from engine.futures import FuturesEngine
    engine = FuturesEngine(queue)
    engine.run()


async def gen_fake_user(session) -> None:
    from faker import Faker
    fkr = Faker()
    
    await session.post(
        BASE_URL + '/auth/register', 
        json={
            'username': fkr.first_name(),
            'email': fkr.email(),
            'password': fkr.word(),
        },
    )


async def gen_fake_orders(session, num_orders: int, cookie: str) -> None:
    import random
    
    randnum = lambda: round(random.random() * 100, 2)
    for _ in range(num_orders):
        # await asyncio.sleep(random.randint(1, 2))
        order_type = random.choice([OrderType.LIMIT, OrderType.MARKET])
        payload = {
            'amount': random.randint(1, 5),
            'instrument': 'BTCUSD',
            'quantity': random.randint(1, 50),
            'market_type': 'futures',
            'order_type': order_type,
            'side': random.choice([Side.BUY, Side.SELL]),
            'take_profit': random.choice([randnum(), None]),
            'stop_loss': random.choice([randnum(), None]),
        }
        
        if order_type == OrderType.LIMIT:
            payload['limit_price'] = randnum()
        
        await session.post(
            BASE_URL + '/order/', 
            json=payload,
            cookies=cookie,
        )
        await asyncio.sleep(0.1)


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
    from config import DEV_MODE
    
    subprocess.run(['alembic', 'upgrade', 'head'], check=True)
    
    async with get_db_session() as sess:
        if DEV_MODE:
            await sess.execute(text("DELETE FROM orders;"))
            await sess.execute(text("DELETE FROM users;"))
        
        await sess.execute(text("SELECT COUNT(*) FROM orders;"))
        await sess.commit()


async def main(gen_fake: bool=False, num_users: int=1, num_orders: int=1) -> None:
    queue = multiprocessing.Queue()
    ps = [
        multiprocessing.Process(target=run_server, args=(queue,), name="server"),
        multiprocessing.Process(target=run_engine, args=(queue,), name="engine"),
    ]
    
    for p in ps:
        p.start()

    await migrate()
    if gen_fake:
        await load_db(num_users, num_orders)

    try:
        while True:
            for p in ps:
                if not p.is_alive():
                    raise Exception(f"{p.name} has died")
            await asyncio.sleep(2)
    except (Exception, KeyboardInterrupt) as e:
        print("[pm][Error] => ", str(e))
        print("Terminating processes")
        
        for p in ps:
            p.terminate()
            p.join()
            print(f"Terminated {p.name}")
                

if __name__ == "__main__":
    asyncio.run(main(True, 1000, 1000))