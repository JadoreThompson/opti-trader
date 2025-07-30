import asyncio
import uvicorn

from json import dumps
from logging import getLogger
from multiprocessing import Process

from config import (
    FUTURES_BOOKS_KEY,
    INSTRUMENT_CHANNEL,
    PAYLOAD_PUSHER_CHANNEL,
    REDIS_CLIENT,
    REDIS_CLIENT_SYNC,
    SPOT_BOOKS_KEY,
)
from engine import FuturesEngine, OrderBook
from engine.orders import SpotOrder, Order
from engine.typing import Queue, SupportsAppend
from enums import ClientEventType, MarketType, StreamEventType
from models import OrderBookSnapshot
from services import PayloadPusher
from utils.utils import get_exc_line

logger = getLogger(__name__)


def run_payload_queue(queue: Queue) -> None:
    while True:
        try:
            item = queue.get()

            if item['topic'] == ClientEventType.PAYLOAD_UPDATE:
                REDIS_CLIENT_SYNC.publish(PAYLOAD_PUSHER_CHANNEL, dumps(item))
            elif isinstance(item['topic'], StreamEventType):
                if item['topic'] == StreamEventType.PRICE:
                    key = FUTURES_BOOKS_KEY if item['data']['market_type'] == MarketType.FUTURES else SPOT_BOOKS_KEY
                    REDIS_CLIENT_SYNC.hset(key, item['data']['instrument'], item['data'])
                    REDIS_CLIENT_SYNC.publish(INSTRUMENT_CHANNEL, item['data'])
            
                REDIS_CLIENT_SYNC.publish(INSTRUMENT_CHANNEL, item['data'])

        except Exception as e:
            logger.error(f"Error: {type(e)} - {str(e)} - line: {get_exc_line()}")


def run_payload_pusher() -> None:
    asyncio.run(PayloadPusher().start())


async def publish_orderbooks(orderbooks: dict[str, OrderBook[Order | SpotOrder]]):
    while True:
        await asyncio.sleep(2)

        snapshots = []
        for instrument, ob in orderbooks.items():
            bids, asks = {}, {}

            bid_levels = [*ob.bid_levels][-5:]
            ask_levels = [*ob.ask_levels][:5]

            for levels, d in ((bid_levels, bids), (ask_levels, asks)):
                for price in levels:
                    quantity = 0
                    cur = ob.bids[price].head

                    while cur:
                        quantity += cur.order.quantity - cur.order.filled_quantity
                        cur = cur.next

                    d[price] = quantity

            snapshot = OrderBookSnapshot(instrument=instrument, bids=bids, asks=asks)
            snapshots.append(snapshot)

        for snapshot in snapshots:
            await REDIS_CLIENT.publish(INSTRUMENT_CHANNEL, snapshot.model_dump())


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
    # await FuturesEngine(pusher_queue=queue, orderbooks=orderbooks).run()
    await asyncio.gather(
        FuturesEngine(pusher_queue=queue, orderbooks=orderbooks).run(),
        publish_orderbooks(orderbooks),
    )


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
