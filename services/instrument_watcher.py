from asyncio import create_task, get_event_loop
from pydantic_core import ValidationError
from config import FUTURES_QUEUE_KEY, REDIS_CLIENT, SPOT_QUEUE_KEY
from .typing import _Instrument


class InstrumentsWatcher:
    def __init__(self) -> None:
        self._is_running = False
        self.run()

    def run(self) -> None:
        loop = get_event_loop()
        if loop.is_running():
            create_task(self._listen())
            self._is_running = True

    async def _listen(self) -> None:
        async with REDIS_CLIENT.pubsub() as ps:
            await ps.subscribe("instrument.new")

            async for message in ps.listen():
                if message["type"] == "subscribe":
                    continue

                try:
                    data = _Instrument(**message["data"])
                    await REDIS_CLIENT.publish(FUTURES_QUEUE_KEY, data.model_dump())
                    await REDIS_CLIENT.publish(SPOT_QUEUE_KEY, data.model_dump())
                except ValidationError:
                    continue

    @property
    def is_running(self):
        if not self._is_running:
            self.run()
        return self._is_running
