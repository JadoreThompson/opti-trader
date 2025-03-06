import asyncio
import json

from redis.asyncio import Redis
from uuid import uuid4
from .manager import LockManager
from .base import LockBase


class Lock(LockBase):
    def __init__(self, client: Redis, key: str, is_manager: bool = True) -> None:
        super().__init__(client, key)
        self._is_running = False
        self._is_manager = is_manager
        self._msg_queue = []
        self._msg_queue_index = 0

        if is_manager:
            self._manager = LockManager(client, key)

    async def run(self):
        if self.is_manager:
            asyncio.create_task(self._manager.run())
        asyncio.create_task(self._listen())

    async def _listen(self):
        async with self._client.pubsub() as ps:
            await ps.subscribe(self._receiver_key)

            async for message in ps.listen():
                if message["type"] == "subscribe":
                    continue

                self._msg_queue.append(json.loads(message["data"]))

    async def acquire(self):
        if not self._is_running:
            await self.run()
            self._is_running = True
            
        payload = {"name": str(uuid4()), "action": "acquire"}
        await self.client.publish(
            self._broadcast_key,
            json.dumps(payload),
        )

        while True:
            try:
                if self._msg_queue[0].get("name") == payload["name"]:
                    self._msg_queue = self._msg_queue[1:]
                    return payload
            except IndexError:
                pass
            finally:
                await asyncio.sleep(1)

    async def release(self):
        await self.client.publish(self._broadcast_key, json.dumps(self._payload))

    async def __aenter__(self):
        # self._payload = await self.acquire()
        # print("Acquisition successfull")
        return True

    async def __aexit__(self, exc_type, exc_value, tcb):
        # self._payload["action"] = "release"
        # await self.release()
        ...
        
    @property
    def client(self):
        return self._client

    @property
    def is_manager(self):
        return self._is_manager

    @property
    def manager(self):
        if self._is_manager:
            return self._manager

    @property
    def key(self):
        return self._key
