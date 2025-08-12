import asyncio
from json import loads

from fastapi import WebSocket

from config import INSTRUMENT_PRICE_QUEUE, REDIS_CLIENT_ASYNC
from enums import InstrumentEventType
from models import PriceUpdate


class InstrumentManager:
    def __init__(self):
        self._channels: dict[tuple[InstrumentEventType, str], set[WebSocket]] = {}
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def subscribe(
        self, channel: InstrumentEventType, instrument: str, ws: WebSocket
    ) -> None:
        self._channels.setdefault((channel, instrument), set()).add(ws)

    def unsubscribe(
        self, channel: InstrumentEventType, instrument: str, ws: WebSocket
    ) -> None:
        self._channels[(channel, instrument)].discard(ws)

    async def listen(self):
        async with REDIS_CLIENT_ASYNC.pubsub() as ps:
            await ps.subscribe(INSTRUMENT_PRICE_QUEUE)
            async for m in ps.listen():
                if m["type"] == "subscribe":
                    self._is_running = True
                    continue

                # parsed_m = PriceUpdate(**loads(m["data"]))
                # asyncio.create_task(self._broadcast(parsed_m.instrument))

    async def _broadcast(self, data: PriceUpdate) -> None:
        for ws in self._channels[data.instrument]:
            await ws.send_json(data.model_dump_json())
