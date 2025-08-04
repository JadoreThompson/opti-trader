import asyncio
import uvicorn

from collections import defaultdict
from json import dumps
from logging import getLogger
from multiprocessing import Process
from typing import Any, Callable, Coroutine, Iterator

from config import (
    FUTURES_BOOKS_KEY,
    INSTRUMENT_EVENTS_CHANNEL,
    PAYLOAD_PUSHER_CHANNEL,
    REDIS_CLIENT,
    REDIS_CLIENT_SYNC,
    SPOT_BOOKS_KEY,
)
from engine import FuturesEngine, SpotEngine, OrderBook
from engine.queue import Queue
from engine.typing import SupportsAppend
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


async def publish_orderbooks(
    payload_iter: Callable[[], Iterator[dict[str, Any]]],
    max_len: int = 10,
    delay: float = 0.5,
):
    while True:

        await asyncio.sleep(delay)

        data = defaultdict(
            lambda: {"bids": defaultdict(int), "asks": defaultdict(int), "events": []}
        )

        for payload in payload_iter():
            bid_asks = data[payload["instrument"]]

            entry_price = (
                payload["limit_price"]
                if payload["limit_price"] is not None
                else payload["price"]
            )

            if payload["status"] in (OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED):
                if payload["side"] == Side.BID:
                    bid_asks["bids"][entry_price] += payload["standing_quantity"]
                else:
                    bid_asks["asks"][entry_price] += payload["standing_quantity"]

            if payload["status"] != OrderStatus.PENDING and payload["open_quantity"]:
                if payload["take_profit"] is not None:
                    if payload["side"] == Side.BID:
                        bid_asks["asks"][payload["take_profit"]] += payload[
                            "open_quantity"
                        ]
                    else:
                        bid_asks["bids"][payload["take_profit"]] += payload[
                            "open_quantity"
                        ]

                if payload["stop_loss"] is not None:
                    if payload["side"] == Side.BID:
                        bid_asks["asks"][payload["stop_loss"]] += payload[
                            "open_quantity"
                        ]
                    else:
                        bid_asks["bids"][payload["stop_loss"]] += payload[
                            "open_quantity"
                        ]

        events = []
        for instrument, book in data.items():
            bids = dict(sorted(book["bids"].items())[:max_len])
            asks = dict(sorted(book["asks"].items())[:max_len])

            events.append(
                InstrumentEvent[OrderBookSnapshot](
                    event_type=InstrumentEventType.ORDERBOOK_UPDATE,
                    instrument=instrument,
                    data=OrderBookSnapshot(bids=bids, asks=asks),
                )
            )

        async with REDIS_CLIENT.pipeline() as pipe:
            for e in events:
                pipe.publish(INSTRUMENT_EVENTS_CHANNEL, e.model_dump_json())
            await pipe.execute()


async def get_prior_books_futures(hkey: str) -> dict[str, OrderBook]:
    book_prices: list[tuple[str, float]] = []

    keys: list[bytes] = await REDIS_CLIENT.hkeys(hkey)
    for book in keys:
        book_prices.append(
            (
                book.decode(),
                await REDIS_CLIENT.hget(hkey, book),
            )
        )

    orderbooks = {instrument: OrderBook(price) for instrument, price in book_prices}
    return orderbooks


async def get_prior_books_spot(hkey: str) -> dict[str, OrderBook]:
    return {}


async def handle_run_futures_engine(queue: SupportsAppend):
    obs = await get_prior_books_futures(FUTURES_BOOKS_KEY)
    engine = FuturesEngine(queue=queue, orderbooks=obs)
    await asyncio.gather(
        engine.run(),
        publish_orderbooks(
            lambda: (pos.payload for pos in [*engine._positions.values()])
        ),
    )


# More to be added.
async def handle_run_spot_engine(queue: SupportsAppend):
    obs = await get_prior_books_spot(SPOT_BOOKS_KEY)
    engine = SpotEngine(queue=queue, orderbooks=obs)
    await asyncio.gather(
        engine.run(),
        publish_orderbooks(
            lambda: (payload for payload in [*engine._payloads.values()])
        ),
    )


def asyncio_run(func: Callable[..., Coroutine], *args, **kwargs):
    asyncio.run(func(*args, **kwargs))


def run_server() -> None:
    uvicorn.run("server.app:app", port=80)

async def main() -> None:
    queue = Queue()

    ps_args = [
        ("server", run_server, ()),
        # ("futures_engine", asyncio_run, (handle_run_futures_engine, queue)),
        ("spot_engine", asyncio_run, (handle_run_spot_engine, queue)),
        ("pusher", run_payload_pusher, ()),
        ("payload_queue", run_payload_queue, (queue,)),
    ]

    ps = [Process(target=target, args=args, name=name) for name, target, args in ps_args]

    for p in ps:
        print(f"Starting process: {p.name}")
        p.start()


    try:
        while True:
            for ind, p in enumerate(ps):
                if not p.is_alive():
                    print(f"Restarting dead process: {p.name}")
                    p.kill()
                    p.join()

                    name, target, args = ps_args[ind]
                    new_p = Process(target=target, args=args, name=name)
                    new_p.start()
                    ps[ind] = new_p

            await asyncio.sleep(0.5)
    except (KeyboardInterrupt, IOError):
        print("Shutting down all processes.")
    finally:
        for p in ps:
            print(f"Killing process: {p.name}")
            p.kill()
            p.join()


if __name__ == "__main__":
    asyncio.run(main())
