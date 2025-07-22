import asyncio
from pydantic import ValidationError
from config import FUTURES_QUEUE_KEY, REDIS_CLIENT, SPOT_QUEUE_KEY
from .typing import _Instrument


class InstrumentsWatcher:
    def __init__(self) -> None:
        self._is_running = False
        self._task: asyncio.Task = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self) -> None:
        if self._task is None and asyncio.get_event_loop().is_running():
            self._task = asyncio.create_task(self._listen())

    async def _listen(self) -> None:
        async with REDIS_CLIENT.pubsub() as ps:
            await ps.subscribe("instrument.new")

            async for message in ps.listen():
                if message["type"] == "subscribe":
                    self._is_running = True
                    continue

                try:
                    data = _Instrument(**message["data"])
                    await REDIS_CLIENT.publish(FUTURES_QUEUE_KEY, data.model_dump())
                    await REDIS_CLIENT.publish(SPOT_QUEUE_KEY, data.model_dump())
                except ValidationError:
                    continue
