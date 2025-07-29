import asyncio
from json import dumps
import uvicorn

from multiprocessing import Process
from typing import Type

from config import PAYLOAD_PUSHER_QUEUE, REDIS_CLIENT_SYNC
from engine import BaseEngine, FuturesEngine, SpotEngine
from engine.typing import Queue, SupportsAppend
from services import PayloadPusher


def run_payload_queue(queue: Queue) -> None:
    while True:
        try:
            item = queue.get()
            REDIS_CLIENT_SYNC.publish(PAYLOAD_PUSHER_QUEUE, dumps(item))
        except Exception as e:
            print(str(e))


def run_payload_pusher() -> None:
    asyncio.run(PayloadPusher().start())


def run_engine(typ: Type[BaseEngine], queue: SupportsAppend) -> None:
    asyncio.run(typ(pusher_queue=queue).run())


def run_server() -> None:
    uvicorn.run("server.app:app", port=80)


async def main() -> None:
    queue = Queue()

    ps_args = (
        (run_engine, (FuturesEngine, queue)),
        (run_server, ()),
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
