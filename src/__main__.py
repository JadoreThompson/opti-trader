import asyncio
from multiprocessing import Process, Queue
from multiprocessing.queues import Queue as MPQueue

import uvicorn

from config import DB_ENGINE
from db_models import Instruments
from engine import SpotEngine
from event_handler import EventHandler
from utils.db import get_db_session_sync


def publish_orderbooks(engine: SpotEngine):
    for ctx in engine._ctxs.values():
        ob = ctx.orderbook

        bids = ob.bids
        for i in range(-1, -11, -1):
            price = ob.bids.l


def run_event_handler(event_queue: MPQueue):
    ev_handler = EventHandler()
    while True:
        event = event_queue.get()

        with get_db_session_sync() as sess:
            ev_handler.process_event(event, sess)

def run_engine(command_queue: MPQueue, event_queue: MPQueue) -> None:
    from engine.event_logger import EventLogger

    engine = SpotEngine(['BTC-USD'])
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
        (run_event_handler, (ev_queue,), "event handler")
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
    # with get_db_session_sync() as sess:
    #     instrument = Instruments(
    #         instrument_id="BTC-USD", symbol="BTC", tick_size=1
    #     )
    #     sess.add(instrument)
    #     sess.commit()
