import os
import time
import uvicorn
import asyncio
import logging
from multiprocessing import Process, Queue

from urllib.parse import quote
from config import DB_URL
from trading_engine.engines.futures import FuturesEngine
from trading_engine.engines.spot import SpotEngine
from trading_engine.db_listener import DBListener


logger = logging.getLogger(__name__)


def db_listener():
    asyncio.run(DBListener(DB_URL.format(quote(os.getenv('DB_PASSWORD')))).start())    


def futures_engine(order_queue: Queue, price_queue):
    asyncio.run(
        FuturesEngine(order_queue)\
            .start(['APPL'], price_queue, quantity=1000, divider=3)
    )


def spot_engine(order_queue: Queue, price_queue: Queue) -> None:
    asyncio.run(SpotEngine(order_queue).start(price_queue=price_queue))


def server(spot_queue: Queue, futures_queue: Queue, price_queue: Queue) -> None:
    from routes.stream import MANAGER
    MANAGER.spot_queue = spot_queue
    MANAGER.futures_queue = futures_queue
    MANAGER.price_queue = price_queue
    
    logger.info('Initialising API server')
    uvicorn.run(
        "api:app", 
        port=8000, 
        host='0.0.0.0', 
        ws_ping_interval=3000.0, 
        ws_ping_timeout=100.0
    )


def main() -> None:
    spot_queue = Queue()
    futures_queue = Queue()
    price_queue = Queue()
    
    funcs = [
        (spot_engine, (spot_queue, price_queue), "Spot Engine"), 
        (futures_engine, (futures_queue, price_queue), "Futures Engine"),
        (server, (spot_queue, futures_queue, price_queue), 'Server'), 
        (db_listener, (), "DB Listener"),
    ]
    
    ps = [Process(target=func, args=args, name=name) for func, args, name in funcs]
    
    for p in ps:
        p.start()
    
    while True:
        try:
            for p in ps:
                if not p.is_alive():
                    logger.error(f"Process ({p.name}) has died unexpectedly")
                    p.join()
                    raise KeyboardInterrupt
                time.sleep(1)
        except KeyboardInterrupt:
            for p in ps:
                p.terminate()
                p.join()
            
            logger.info('All processes terminated')
            raise


if __name__ == '__main__':
    main()
        