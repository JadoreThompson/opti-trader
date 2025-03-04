import asyncio
import json

from collections import deque
from typing import Literal
from sqlalchemy import update
from config import ORDER_UPDATE_CHANNEL, REDIS_CLIENT
from db_models import Orders
from utils.db import get_db_session
from .utils import dump_order


class Pusher:
    def __init__(
        self,
        delay: float = 2,
    ) -> None:
        "Delay in seconds"
        self._slow_queue = deque()
        self._fast_queue = deque()
        self._delay = delay
        self._is_running: bool = False
        self._slow_running: bool = False
        self._fast_running: bool = False

    async def run(self) -> None:
        # loop = asyncio.get_running_loop()
        # loop.create_task(self._push_fast())
        # loop.create_task(self._push_slow())
        asyncio.create_task(self._push_fast())
        asyncio.create_task(self._push_slow())
        await asyncio.sleep(2)

    def append(
        self, obj: dict | list[dict], mode: Literal["lazy", "fast"] = "lazy"
    ) -> None:
        if mode == "lazy":
            if isinstance(obj, list):
                self._slow_queue.extend(obj)
            else:
                self._slow_queue.append(obj)
        else:
            if isinstance(obj, list):
                self._fast_queue.extend(obj)
            else:
                self._fast_queue.append(obj)

    async def _push_slow(self) -> None:
        self._slow_running = True
        while True:
            if self._slow_queue:
                try:
                    async with get_db_session() as sess:
                        await sess.execute(update(Orders), self._slow_queue)
                        await sess.commit()

                    async with REDIS_CLIENT.pipeline() as pipe:
                        for item in self._slow_queue:
                            await pipe.publish(ORDER_UPDATE_CHANNEL, dump_order(item))

                        await pipe.execute()

                    self._slow_queue.clear()
                except Exception as e:
                    print(
                        f"[pusher][run] => Error: type - ",
                        type(e),
                        "content - ",
                        str(e),
                    )
            await asyncio.sleep(self._delay)

    async def _push_fast(self) -> None:
        self._fast_running = True
        while True:
            if self._fast_queue:
                try:
                    async with get_db_session() as sess:
                        await sess.execute(update(Orders), [self._fast_queue])
                        await sess.commit()
                        
                    async with REDIS_CLIENT.pipeline() as pipe:
                        for item in self._fast_queue.copy():
                            await pipe.publish(ORDER_UPDATE_CHANNEL, dump_order(item))

                        await pipe.execute()
                    self._fast_queue.clear()
                except Exception as e:
                    print("[pusher][fast] - ", type(e), str(e))
                
                await asyncio.sleep(0.5)    

    @property
    def is_running(self) -> bool:
        return self._fast_running and self._slow_running
