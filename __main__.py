import asyncio
import uvicorn

from json import dumps
from logging import getLogger
from multiprocessing import Process

from config import (
    FUTURES_BOOKS_KEY,
    PAYLOAD_PUSHER_CHANNEL,
    REDIS_CLIENT,
    REDIS_CLIENT_SYNC,
)
from engine import FuturesEngine, OrderBook
from engine.typing import Queue, SupportsAppend
from services import PayloadPusher
from utils.utils import get_exc_line

logger = getLogger(__name__)


def run_payload_queue(queue: Queue) -> None:
    while True:
        try:
            item = queue.get()
            REDIS_CLIENT_SYNC.publish(PAYLOAD_PUSHER_CHANNEL, dumps(item))
        except Exception as e:
            logger.error(f"Error: {type(e)} - {str(e)} - line: {get_exc_line()}")


def run_payload_pusher() -> None:
    asyncio.run(PayloadPusher().start())


async def handle_run_futures_engine(queue: SupportsAppend) -> None:
    book_prices: list[tuple[str, float]] = []

    keys: list[bytes] = await REDIS_CLIENT.hkeys(FUTURES_BOOKS_KEY)
    for book in keys:
        book_prices.append(
            (
                book.decode(),
                await REDIS_CLIENT.hget(FUTURES_BOOKS_KEY, book),
            )
        )

    orderbooks = {instrument: OrderBook(price) for instrument, price in book_prices}
    await FuturesEngine(pusher_queue=queue, orderbooks=orderbooks).run()


def run_futures_engine(queue: SupportsAppend) -> None:
    asyncio.run(handle_run_futures_engine(queue))


def run_server() -> None:
    uvicorn.run("server.app:app", port=80)


async def main() -> None:
    queue = Queue()

    ps_args = (
        (run_server, ()),
        (run_futures_engine, (queue,)),
        (run_payload_pusher, ()),
        (run_payload_queue, (queue,)),
    )
    ps = [Process(target=target, args=args) for target, args in ps_args]

    for p in ps:
        p.start()

    try:
        while True:
            for ind, p in enumerate(ps):
                if not p.is_alive:
                    p.kill()
                    p.join()

                    target, args = ps_args[ind]
                    new_p = Process(target=target, args=args)
                    new_p.start()
                    ps[ind] = new_p

            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in ps:
            p.kill()
            p.join()


if __name__ == "__main__":
    asyncio.run(main())
