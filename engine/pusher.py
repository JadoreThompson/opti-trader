import asyncio
import json

from collections import deque
from sqlalchemy import case, update
from typing import Literal
from r_mutex import Lock

from api.routes.order.models import BalancePayload
from config import BALANCE_UPDATE_CHANNEL, ORDER_UPDATE_CHANNEL, REDIS_CLIENT
from db_models import Orders, Users
from utils.db import get_db_session
from .utils import dump_obj


class Pusher:
    """
    Consolidates updates to records within the database and publishes them to the pubsub
    channel for real-time user updates. It manages different types of updates (fast,
    slow, and balance updates) with configurable delays and batch processing.

    Attributes:
        lock (Lock): Mutex lock for safe concurrent access to the orders and users table.
        batch_size (int): Number of records to process per update cycle.
        _slow_queue (deque): Queue for non-urgent order updates.
        _fast_queue (deque): Queue for urgent order updates.
        _balance_queue (deque): Queue for user balance updates.
        _slow_delay (float): Delay between non-urgent order updates.
        _fast_delay (float): Delay between urgent order updates.
        _balance_delay (float): Delay between balance updates.
        _is_running (bool): Flag indicating whether the pusher is running.
        _slow_running (bool): Flag indicating whether slow updates are running.
        _fast_running (bool): Flag indicating whether fast updates are running.
        _balance_running (bool): Flag indicating whether balance updates are running.
    """

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
        """Initialise and run the pusher"""
        asyncio.create_task(self._push_fast())
        asyncio.create_task(self._push_slow())
        asyncio.create_task(self._push_balance())
        await asyncio.sleep(2)

    def append(
        self,
        obj: dict | list[dict],
        topic: Literal["balance", "order"] = "order",
        speed: Literal["slow", "fast"] = "slow",
    ) -> None:
        """
        Appends the obj(s) to a queue to be updated
        
        Args:
            topic ('balance', 'order') - Balance update or order update
            speed ('slow', 'fast')
        """
        if topic == "order":
            if speed == "slow":
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
        """
        Conducts updates to records and updates to the pubsub channel
        periodically based on the slow delay attribute.
        """
        self._slow_running = True
        while True:
            if self._slow_queue:
                collection = []
                for _ in range(self.batch_size):
                    try:
                        collection.append(self._slow_queue.popleft())
                    except IndexError:
                        break

                async with self.lock:
                    async with get_db_session() as sess:
                        await sess.execute(update(Orders), collection)
                        await sess.commit()

                async with REDIS_CLIENT.pipeline() as pipe:
                    for item in collection:
                        await pipe.publish(ORDER_UPDATE_CHANNEL, dump_obj(item))

                    await pipe.execute()

            await asyncio.sleep(self._slow_delay)

    async def _push_fast(self) -> None:
        """
        Conducts updates to records and updates to the pubsub channel
        periodically based on the fast delay attribute.
        """
        self._fast_running = True
        while True:
            if self._fast_queue:
                collection = []
                for _ in range(self.batch_size):
                    try:
                        collection.append(self._fast_queue.popleft())
                    except IndexError:
                        break

                async with self.lock:
                    async with get_db_session() as sess:
                        await sess.execute(update(Orders), collection)
                        await sess.commit()

                async with REDIS_CLIENT.pipeline() as pipe:
                    for item in collection:
                        await pipe.publish(ORDER_UPDATE_CHANNEL, dump_obj(item))
                    await pipe.execute()

            await asyncio.sleep(self._fast_delay)

    async def _push_balance(self):
        """
        Conducts updates to records and updates to the pubsub channel
        of the user's balance periodically based on the balance delay
        attribute.
        """
        self._balance_running = True

        while True:
            if self._balance_queue:
                collection = []
                for _ in range(self.batch_size):
                    try:
                        collection.append(self._balance_queue.popleft())
                    except IndexError:
                        break

                async with self.lock:
                    async with get_db_session() as sess:
                        res = await sess.execute(
                            update(Users)
                            .where(
                                Users.user_id.in_([u["user_id"] for u in collection])
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

            await asyncio.sleep(self._balance_delay)

    @property
    def is_running(self) -> bool:
        return self._fast_running and self._slow_running and self._balance_running
