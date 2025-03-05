import asyncio

from collections import deque
from sqlalchemy import case, update
from typing import Literal

from config import BALANCE_UPDATE_CHANNEL, DB_LOCK, ORDER_UPDATE_CHANNEL, REDIS_CLIENT
from db_models import Orders, Users
from utils.db import get_db_session
from .utils import dump_obj


# To improve performance, multiple processes
# or even distributed processes can be leveraged
# through PubSub or Kafka
class Pusher:
    def __init__(
        self,
        lock,
        slow_delay: float = 2.0,
        fast_delay: float = 0.8,
        balance_delay: float = 3.5,
    ) -> None:
        "Delay in seconds"
        self.lock = lock
        self._slow_queue = deque()
        self._fast_queue = deque()
        self._balance_queue = deque()

        self._slow_delay = slow_delay
        self._fast_delay = fast_delay
        self._balance_delay = balance_delay

        self._is_running: bool = False
        self._slow_running: bool = False
        self._fast_running: bool = False
        self._balance_running: bool = False

    async def run(self) -> None:
        asyncio.create_task(self._push_fast())
        asyncio.create_task(self._push_slow())
        asyncio.create_task(self._update_balance())
        await asyncio.sleep(2)

    def append(
        self,
        obj: dict | list[dict],
        gate: Literal["balance", "order"] = "order",
        mode: Literal["lazy", "fast"] = "lazy",
    ) -> None:
        if gate == "order":
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
        else:
            # print("appending to balance queue")
            if isinstance(obj, list):
                self._balance_queue.extend(obj)
            else:
                self._balance_queue.append(obj)

    async def _push_slow(self) -> None:
        self._slow_running = True
        while True:
            if self._slow_queue:
                try:
                    async with self.lock:
                        print("[pusher][slow] I've got the lock")
                        collection = [*self._slow_queue]
                        async with get_db_session() as sess:
                            # await sess.execute(update(Orders), [*self._slow_queue])
                            await sess.execute(update(Orders), collection)
                            await sess.commit()
                    # print("[pusher][slow] - Done updating in DB")
                    async with REDIS_CLIENT.pipeline() as pipe:
                        # for item in self._slow_queue:
                        for item in collection:
                            await pipe.publish(ORDER_UPDATE_CHANNEL, dump_obj(item))

                        await pipe.execute()

                    self._slow_queue.clear()
                except Exception:
                    import traceback

                    traceback.print_exc()

            await asyncio.sleep(self._slow_delay)

    async def _push_fast(self) -> None:
        self._fast_running = True
        while True:
            if self._fast_queue:
                try:
                    async with self.lock:
                        print("[pusher][fast] I've got the lock")
                        collection = [*self._fast_queue]
                        async with get_db_session() as sess:
                            await sess.execute(update(Orders), collection)
                            await sess.commit()
                    # print("[pusher][fast] - Done updating in DB")
                    async with REDIS_CLIENT.pipeline() as pipe:
                        # for item in self._fast_queue.copy():
                        for item in collection:
                            await pipe.publish(ORDER_UPDATE_CHANNEL, dump_obj(item))
                        await pipe.execute()

                    self._fast_queue.clear()
                except Exception:
                    import traceback

                    traceback.print_exc()

            await asyncio.sleep(self._fast_delay)

    async def _update_balance(self):
        self._balance_running = True

        while True:
            if self._balance_queue:
                collection = [*self._balance_queue]
                try:
                    print("-" * 10)

                    async with self.lock:
                        print("[pusher][update balance] I've got the lock")
                        async with get_db_session() as sess:
                            await sess.execute(update(Users).values(balance=10000000))
                            await sess.commit()
                    print("done")

                    # print(collection)
                    # async with self._lock:
                    #     async with get_db_session() as sess:
                    #         await sess.execute(
                    #             update(Users)
                    #             .where(
                    #                 Users.user_id.in_(
                    #                     [u["user_id"] for u in collection]
                    #                 )
                    #             )
                    #             .values(
                    #                 balance=case(
                    #                     {
                    #                         u["user_id"]: Users.balance + u["amount"]
                    #                         for u in collection
                    #                     },
                    #                     value=Users.user_id,
                    #                 )
                    #             )
                    #         )

                    #         await sess.commit()
                    
                    async with REDIS_CLIENT.pipeline() as pipe:
                        for item in collection:
                            await pipe.publish(BALANCE_UPDATE_CHANNEL, dump_obj(item))
                        await pipe.execute()

                    self._balance_queue.clear()
                except Exception as e:
                    print(e)
                    import traceback

                    traceback.print_exc()

            await asyncio.sleep(self._balance_delay)

    @property
    def is_running(self) -> bool:
        return self._fast_running and self._slow_running and self._balance_running
