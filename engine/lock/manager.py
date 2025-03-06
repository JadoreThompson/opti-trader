import json
import asyncio
import logging

from typing import Callable
from redis.asyncio import Redis
from .base import LockBase

logger = logging.getLogger(__name__)


class LockManager(LockBase):
    def __init__(self, client: Redis, key, timeout: float = 1.0) -> None:
        super().__init__(client, key)
        self._queue = []
        self._current = {}
        self._timeout = timeout
        self._received_release: bool = False
        self._task: asyncio.Task = None
        self._lock = asyncio.Lock()

    async def run(self) -> None:
        handlers: dict[str, Callable] = {
            "acquire": self._handle_acquire,
            "release": self._handle_release,
        }

        async with self._client.pubsub() as ps:
            await ps.subscribe(self._broadcast_key)
            async for message in ps.listen():
                if message["type"] == "subscribe":
                    continue

                payload: dict = json.loads(message["data"])
                await handlers[payload["action"]](payload, data=message["data"])
                
    async def _handle_acquire(self, payload: dict, data: bytes) -> None:
        if not self._current:
            self._current = payload
            await self._client.publish(
                self._receiver_key, json.dumps({"name": payload["name"]})
            )
        else:
            self._queue.append(payload)

    async def _handle_release(self, payload: dict, **kwargs) -> None:
        if payload["name"] == self._current.get("name"):
            try:
                self._current = self._queue.pop(0)
            except IndexError:
                self._current = {}

            await self._client.set(self._current_key, json.dumps(self._current))
            await self._client.publish(
                self._receiver_key, json.dumps({"name": self._current.get("name", "-")})
            )
