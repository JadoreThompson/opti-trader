import asyncio
from threading import Thread
import time
from multiprocessing import Process, Queue
from multiprocessing.queues import Queue as MPQueue

import uvicorn

from config import INSTRUMENT_EVENT_CHANNEL, REDIS_CLIENT
from engine import SpotEngine
from engine.models import Event
from enums import InstrumentEventType
from event_handler import EventHandler
from models import InstrumentEvent, OrderBookSnapshot
from orderbook_duplicator import OrderBookReplicator
from utils.db import get_db_session_sync


def publish_orderbooks(orderbooks: dict[str, OrderBookReplicator], delay: float = 1.0):
    while True:
        with REDIS_CLIENT.pipeline() as pipe:
            for instrument_id, replicator in orderbooks.items():
                snapshot = replicator.snapshot()
                bids, asks = snapshot["bids"], snapshot["asks"]

                event = InstrumentEvent(
                    event_type=InstrumentEventType.ORDERBOOK,
                    instrument_id=instrument_id,
                    data=OrderBookSnapshot(bids=bids, asks=asks),
                )

                pipe.publish(INSTRUMENT_EVENT_CHANNEL, event.model_dump_json())

            pipe.execute()

        time.sleep(delay)


def run_event_handler(event_queue: MPQueue):
    ev_handler = EventHandler()
    orderbooks: dict[str, OrderBookReplicator] = {}

    th = Thread(target=publish_orderbooks, args=(orderbooks,))
    th.start()

    while True:
        event: Event = event_queue.get()

        with get_db_session_sync() as sess:
            ev_handler.process_event(event, sess)

        if event.instrument_id not in orderbooks:
            orderbooks[event.instrument_id] = OrderBookReplicator()
        replicator = orderbooks[event.instrument_id]
        replicator.process_event(event)


def run_engine(command_queue: MPQueue, event_queue: MPQueue) -> None:
    from engine.event_logger import EventLogger

    engine = SpotEngine(["BTC-USD"])
    EventLogger.queue = event_queue

    while True:
        command = command_queue.get()
        engine.process_command(command)


def run_server(command_queue: MPQueue):
    import config

    config.COMMAND_QUEUE = command_queue
    uvicorn.run("server.app:app", port=80)


async def main():
    command_queue = Queue()
    ev_queue = Queue()

    p_configs = (
        (run_server, (command_queue,), "http server"),
        (run_engine, (command_queue, ev_queue), "spot engine"),
        (run_event_handler, (ev_queue,), "event handler"),
    )
    ps = [Process(target=func, args=args, name=name) for func, args, name in p_configs]

    for p in ps:
        print("[INFO]: Process", p.name, "has started")
        p.start()

    try:
        while True:
            for ind, p in enumerate(ps):
                # print(p)
                if not p.is_alive():
                    print("[INFO]:", p.name, "has died")
                    p.kill()
                    p.join()
                    target, args, name = p_configs[ind]
                    ps[ind] = Process(target=target, args=args, name=name)
                    ps[ind].start()
                    print("[INFO]: Restarted process for", p.name)

            await asyncio.sleep(10_000_000)
    except BaseException as e:
        if not isinstance(e, KeyboardInterrupt):
            print(e)
    finally:
        for p in ps:
            p.kill()
            p.join()


if __name__ == "__main__":
    asyncio.run(main())
    # uvicorn.run("server.app:app", port=80, reload=True)
