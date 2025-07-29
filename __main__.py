import asyncio
import uvicorn

from multiprocessing import Process
from typing import Type
from engine import BaseEngine, FuturesEngine, SpotEngine


def run_engine(typ: Type[BaseEngine]) -> None:
    asyncio.run(typ().run())


def run_server() -> None:
    uvicorn.run("server.app:app", port=80)


async def main() -> None:
    ps_args = (
        (run_engine, (FuturesEngine,)),
        (run_server, ()),
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
