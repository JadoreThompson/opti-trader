import asyncio
from collections import defaultdict
import uvicorn

from json import dumps
from logging import getLogger
from multiprocessing import Process

from config import (
    FUTURES_BOOKS_KEY,
    INSTRUMENT_EVENTS_CHANNEL,
    PAYLOAD_PUSHER_CHANNEL,
    REDIS_CLIENT,
    REDIS_CLIENT_SYNC,
)
from engine import FuturesEngine, OrderBook
from engine.typing import Queue, SupportsAppend
from enums import InstrumentEventType, OrderStatus, Side
from models import InstrumentEvent, OrderBookSnapshot
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


async def publish_orderbooks(engine: FuturesEngine):
    while True:
        await asyncio.sleep(1)

        data = defaultdict(
            lambda: {"bids": defaultdict(int), "asks": defaultdict(int), "events": []}
        )

        for pos in engine._positions.values():
            payload = pos.payload
            d = data[pos.instrument]
            entry_price = (
                payload["limit_price"]
                if payload["limit_price"] is not None
                else payload["price"]
            )

            if pos.status in (OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED):
                if payload["side"] == Side.BID:
                    d["bids"][entry_price] += payload["standing_quantity"]
                else:
                    d["asks"][entry_price] += payload["standing_quantity"]

            if pos.status != OrderStatus.PENDING and pos.open_quantity:
                if payload["take_profit"] is not None:
                    if payload["side"] == Side.BID:
                        d["asks"][payload["take_profit"]] += pos.open_quantity
                    else:
                        d["bids"][payload["take_profit"]] += pos.open_quantity

                if payload["stop_loss"] is not None:
                    if payload["side"] == Side.BID:
                        d["asks"][payload["stop_loss"]] += pos.open_quantity
                    else:
                        d["bids"][payload["stop_loss"]] += pos.open_quantity

        events = []
        for instrument in data:
            events.append(
                InstrumentEvent[OrderBookSnapshot](
                    event_type=InstrumentEventType.ORDERBOOK_UPDATE,
                    instrument=instrument,
                    data=OrderBookSnapshot(
                        bids=data[instrument]["bids"], asks=data[instrument]["asks"]
                    ),
                )
            )

        async with REDIS_CLIENT.pipeline() as pipe:
            for e in events:
                pipe.publish(INSTRUMENT_EVENTS_CHANNEL, e.model_dump_json())
            await pipe.execute()


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
    engine = FuturesEngine(pusher_queue=queue, orderbooks=orderbooks)

    await asyncio.gather(engine.run(), publish_orderbooks(engine))


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
