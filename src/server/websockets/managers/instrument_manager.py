import asyncio
from json import loads
from typing import Iterable

from fastapi import WebSocket

from config import INSTRUMENT_EVENT_CHANNEL, REDIS_CLIENT_ASYNC
from enums import InstrumentEventType
from models import InstrumentEvent, OrderBookEvent, PriceEvent, TradeEvent


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
        key = (channel, instrument)
        if key not in self._channels:
            self._channels[(channel, instrument)] = set()
        self._channels[(channel, instrument)].add(ws)

    def unsubscribe(
        self, channel: InstrumentEventType, instrument: str, ws: WebSocket
    ) -> None:
        key = (channel, instrument)
        if key in self._channels:
            self._channels[key].discard(ws)

    async def listen(self):
        async with REDIS_CLIENT_ASYNC.pubsub() as ps:
            await ps.subscribe(INSTRUMENT_EVENT_CHANNEL)
            async for m in ps.listen():
                if m["type"] == "subscribe":
                    self._is_running = True
                    continue

                parsed_m = InstrumentEvent(**loads(m))
                wsockets = self._channels.get(
                    (parsed_m.event_type, parsed_m.instrument_id)
                )
                asyncio.create_task(self._broadcast(parsed_m, wsockets))

    async def _broadcast(
        self,
        event_data: PriceEvent | TradeEvent | OrderBookEvent,
        wsockets: Iterable[WebSocket],
    ):
        for ws in wsockets:
            await ws.send_json(event_data.model_dump_json())
