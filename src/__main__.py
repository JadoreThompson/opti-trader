import asyncio
from multiprocessing import Process, Queue
from multiprocessing.queues import Queue as MPQueue

import uvicorn

from engine import SpotEngine


def run_engine(command_queue: MPQueue, event_queue: MPQueue) -> None:
    from engine.event_logger import EventLogger

    engine = SpotEngine()
    EventLogger.queue = event_queue

    while True:
        command = command_queue.get()
        engine.process_command(command)


def run_server(command_queue: MPQueue):
    import config

    config.COMMAND_QUEUE = command_queue
    uvicorn.run("server.app:app", port=80, reload=True)


async def main():
    command_queue = Queue()

    p_configs = (
        (run_server, (command_queue,), "http server"),
        (run_engine, (command_queue, Queue()), "spot engine"),
    )
    ps = [Process(target=func, args=args, name=name) for func, args, name in p_configs]

    # print(1)
    for p in ps:
        print("[INFO]: Process", p.name, "has started")
        p.start()
    # print(2)

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
