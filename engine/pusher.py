import asyncio
import json
import traceback

from collections import deque
from sqlalchemy import case, update
from typing import Literal
from r_mutex import Lock

from api.routes.order.models import BalancePayload
from config import BALANCE_UPDATE_CHANNEL, ORDER_UPDATE_CHANNEL, REDIS_CLIENT
from db_models import Orders, Users
from utils.db import get_db_session
from .utils import dump_obj


# To improve performance, leverage celery
class Pusher:
    def __init__(
        self,
        lock: Lock,
        slow_delay: float = 2.0,
        fast_delay: float = 0.8,
        balance_delay: float = 3.5,
        batch_size: int = 100,
    ) -> None:
        "Delay in seconds"
        self.lock = lock
        self.batch_size = batch_size
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
            if isinstance(obj, list):
                self._balance_queue.extend(obj)
            else:
                self._balance_queue.append(obj)

    async def _push_slow(self) -> None:
        self._slow_running = True
        while True:
            if self._slow_queue:
                collection = []
                for _ in range(self.batch_size):
                    try:
                        collection.append(self._slow_queue.popleft())
                    except IndexError:
                        break

                try:
                    async with self.lock:
                        async with get_db_session() as sess:
                            await sess.execute(update(Orders), collection)
                            await sess.commit()

                    async with REDIS_CLIENT.pipeline() as pipe:
                        for item in collection:
                            await pipe.publish(ORDER_UPDATE_CHANNEL, dump_obj(item))

                        await pipe.execute()
                except Exception:
                    traceback.print_exc()

            await asyncio.sleep(self._slow_delay)

    async def _push_fast(self) -> None:
        self._fast_running = True
        while True:
            if self._fast_queue:
                collection = []
                for _ in range(self.batch_size):
                    try:
                        collection.append(self._fast_queue.popleft())
                    except IndexError:
                        break

                try:
                    async with self.lock:
                        async with get_db_session() as sess:
                            await sess.execute(update(Orders), collection)
                            await sess.commit()

                    async with REDIS_CLIENT.pipeline() as pipe:
                        for item in collection:
                            await pipe.publish(ORDER_UPDATE_CHANNEL, dump_obj(item))
                        await pipe.execute()
                except Exception:
                    traceback.print_exc()

            await asyncio.sleep(self._fast_delay)

    async def _update_balance(self):
        self._balance_running = True

        while True:
            if self._balance_queue:
                collection = []
                for _ in range(self.batch_size):
                    try:
                        collection.append(self._balance_queue.popleft())
                    except IndexError:
                        break

                try:
                    async with self.lock:
                        async with get_db_session() as sess:
                            res = await sess.execute(
                                update(Users)
                                .where(
                                    Users.user_id.in_(
                                        [u["user_id"] for u in collection]
                                    )
                                )
                                .values(
                                    balance=case(
                                        {
                                            u["user_id"]: Users.balance + u["amount"]
                                            for u in collection
                                        },
                                        value=Users.user_id,
                                    )
                                )
                                .returning(Users.user_id, Users.balance)
                            )
                            updates = res.all()
                            await sess.commit()

                    async with REDIS_CLIENT.pipeline() as pipe:
                        for item in updates:
                            await pipe.publish(
                                BALANCE_UPDATE_CHANNEL,
                                json.dumps(
                                    BalancePayload(
                                        user_id=str(item[0]), balance=item[1]
                                    ).model_dump()
                                ),
                            )
                        await pipe.execute()

                except Exception:
                    traceback.print_exc()

            await asyncio.sleep(self._balance_delay)

    @property
    def is_running(self) -> bool:
        return self._fast_running and self._slow_running and self._balance_running
