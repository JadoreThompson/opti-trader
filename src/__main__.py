import asyncio
from threading import Thread
import time
from multiprocessing import Process, Queue
from multiprocessing.queues import Queue as MPQueue
from uuid import uuid4

from sqlalchemy import select
import uvicorn

from config import CASH_BALANCE_HKEY, INSTRUMENT_EVENT_CHANNEL, REDIS_CLIENT
from db_models import Instruments
from engine import SpotEngine
from engine.enums import CommandType
from engine.models import Command, Event, NewSingleOrder
from enums import InstrumentEventType, OrderStatus, OrderType, Side, StrategyType
from event_handler import EventHandler
from models import InstrumentEvent, OrderBookSnapshot
from orderbook_duplicator import OrderBookReplicator
from utils.db import get_db_session_sync
from utils.utils import get_instrument_balance_hkey, get_instrument_escrows_hkey


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


def lay_orders(engine: SpotEngine, instrument_id: str):
    REDIS_CLIENT.hset(get_instrument_balance_hkey(instrument_id), "layer", 2000)
    REDIS_CLIENT.hset(get_instrument_escrows_hkey(instrument_id), "layer", 0)

    for i in range(200):
        data = NewSingleOrder(
            strategy_type=StrategyType.SINGLE,
            instrument_id=instrument_id,
            order={
                "user_id": "layer",
                "order_id": str(uuid4()),
                "instrument": instrument_id,
                "order_type": OrderType.LIMIT,
                "side": Side.ASK,
                "quantity": 10,
                "executed_quantity": 0,
                "limit_price": i,
                "status": OrderStatus.PENDING,
            },
        )
        cmd = Command(command_type=CommandType.NEW_ORDER, data=data)
        engine.process_command(cmd)


def run_engine(command_queue: MPQueue, event_queue: MPQueue) -> None:
    from engine.event_logger import EventLogger

    with get_db_session_sync() as sess:
        insts = sess.execute(select(Instruments.instrument_id)).scalars().all()

    engine = SpotEngine(insts)
    EventLogger.queue = event_queue

    for inst in insts:
        lay_orders(engine, inst)

    while True:
        command: Command = command_queue.get()
        engine.process_command(command)
        print(command)
        if command.command_type == CommandType.NEW_INSTRUMENT:
            lay_orders(engine, command.data.instrument_id)

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
