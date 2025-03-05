import asyncio
import json
import inspect

from aioredis import Channel
from redis.asyncio import Redis
from typing import Literal

from config import REDIS_CLIENT


class Lock:
    def __init__(self, client: Redis, channel: str, mode: Literal["lazy", "fast"] = "fast") -> None:
        self._is_running: bool = False
        self._channel = channel
        self._client = client
        self._queue: list[str] = []
        
        if mode == 'fast':
            asyncio.get_running_loop().create_task(self._run())
        
    async def _run(self) -> None:
        await self._load_queue()
        asyncio.get_running_loop().create_task(self._listen())
        
    async def _load_queue(self) -> None:
        ex_queue = await REDIS_CLIENT.get(f"{self._channel}.queue")
        
        if ex_queue:
            self._queue = json.loads(ex_queue)
        
    async def _listen(self) -> None:
        async with self._client.pubsub() as ps:
            await ps.subscribe(self._channel)
            self._is_running = True
            async for message in ps.listen():
                if message['type'] == 'subscribe':
                    continue
                
                
    async def __aenter__(self):
        print(inspect.stack()[1].function)
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        await REDIS_CLIENT.publish(self._channel, "")
        
    @property
    def is_running(self) -> bool:
        return self._is_running
        
    @property
    def channel(self) -> str:
        return self._channel
    
    @property
    def client(self) -> Redis:
        return self._client