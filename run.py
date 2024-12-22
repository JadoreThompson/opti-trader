import uvicorn
import asyncio
import logging
from multiprocessing import Process, Queue

from config import DB_URL
from engine.matching_engine import MatchingEngine
from engine.db_listener import DBListener


logger = logging.getLogger(__name__)


def db_listener():
    asyncio.run(DBListener(DB_URL).start())    


def engine(order_queue: Queue, price_queue: Queue) -> None:
    asyncio.run(MatchingEngine(order_queue).main(price_queue))


def server(order_queue: Queue, price_queue: Queue) -> None:
    from routes.stream import MANAGER
    MANAGER.order_queue = order_queue
    MANAGER.price_queue = price_queue
    
    logger.info('Initialising API server')
    uvicorn.run(
        "app:app", 
        port=8000, 
        host='0.0.0.0', 
        ws_ping_interval=3000.0, 
        ws_ping_timeout=100.0
    )


def main() -> None:
    order_queue = Queue()
    price_queue = Queue()
    
    funcs = [
        (server, (order_queue, price_queue)), 
        (engine, (order_queue, price_queue)), 
        (db_listener, ())
    ]
    ps = [Process(target=func, args=args) for func, args in funcs]
    
    for p in ps:
        p.start()
    
    for p in ps:
        p.join()


if __name__ == '__main__':
    main()
        