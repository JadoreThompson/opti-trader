import asyncio

from collections import defaultdict
from fastapi import WebSocket
from json import loads
from logging import getLogger

from config import (
    FUTURES_BOOKS_KEY,
    INSTRUMENT_EVENTS_CHANNEL,
    REDIS_CLIENT,
    SPOT_BOOKS_KEY,
)
from models import (
    InstrumentEvent,
    InstrumentEventUnion,
    OrderBookSnapshot,
    PriceUpdate,
    RecentTrade,
)
from utils.utils import get_exc_line
from enums import InstrumentEventType, MarketType
from .models import InstrumentStreamMessage


logger = getLogger(__name__)


class ClientManager:
    def __init__(self, delay: int = 5):
        self._delay = delay
        self._tasks: dict[str, asyncio.Task] = {}
        self._is_running = False
        self._channels: dict[str, dict[InstrumentEventType, set[WebSocket]]] = (
            defaultdict(lambda: defaultdict(set))
        )
        self._orderbook_queue = asyncio.Queue()
        self._price_queue = asyncio.Queue()
        self._recent_trades_queue = asyncio.Queue()
        self._instruments: set[tuple[str, str]] = set()

    @property
    def is_running(self) -> bool:
        return self._is_running

    async def run(self) -> None:
        if not self._is_running:
            await asyncio.gather(
                self._listen(),
                self._listen_to_orderbook_queue(),
                self._listen_to_price_queue(),
                self._listen_to_recent_trades_queue(),
            )

    def subscribe(
        self, instrument: str, event_type: InstrumentEventType, ws: WebSocket
    ) -> None:
        coll = self._channels[instrument][event_type]
        if ws not in coll:
            coll.add(ws)

    def unsubscribe(
        self, instrument: str, event_type: InstrumentEventType, ws: WebSocket
    ) -> None:
        coll = self._channels[instrument][event_type]
        if ws in coll:
            coll.discard(ws)

    async def _listen(self) -> None:
        async with REDIS_CLIENT.pubsub() as ps:
            await ps.subscribe(INSTRUMENT_EVENTS_CHANNEL)
            async for m in ps.listen():
                if m["type"] == "subscribe":
                    self._is_running = True
                    continue

                event: InstrumentEventUnion = InstrumentEvent(**loads(m["data"]))

                if event.event_type == InstrumentEventType.ORDERBOOK_UPDATE:
                    self._orderbook_queue.put_nowait(event)
                elif event.event_type == InstrumentEventType.PRICE_UPDATE:
                    self._instruments.add(
                        (
                            (
                                FUTURES_BOOKS_KEY
                                if event.data['market_type'] == MarketType.FUTURES
                                else SPOT_BOOKS_KEY
                            ),
                            event.instrument,
                        )
                    )
                    self._price_queue.put_nowait(event)
                elif event.event_type == InstrumentEventType.RECENT_TRADE:
                    self._recent_trades_queue.put_nowait(event)
                else:
                    logger.info(f"Unrecognised event type {event.event_type}")

    async def _listen_to_orderbook_queue(
        self,
    ) -> None:
        while True:
            item: InstrumentEvent[OrderBookSnapshot] = await self._orderbook_queue.get()
            snapshot = item.data

            for ws in self._channels[item.instrument][
                InstrumentEventType.ORDERBOOK_UPDATE
            ]:
                await ws.send_text(
                    InstrumentStreamMessage(
                        event_type=InstrumentEventType.ORDERBOOK_UPDATE,
                        data=snapshot,
                    ).model_dump_json()
                )

    async def _listen_to_price_queue(
        self,
    ) -> None:
        while True:
            item: InstrumentEvent[PriceUpdate] = await self._price_queue.get()
            price = str(item.data['price'])
            for ws in self._channels[item.instrument][InstrumentEventType.PRICE_UPDATE]:
                await ws.send_text(
                    InstrumentStreamMessage(
                        event_type=InstrumentEventType.PRICE_UPDATE,
                        data=price,
                    ).model_dump_json()
                )

    async def _listen_to_recent_trades_queue(
        self,
    ) -> None:
        while True:
            item: InstrumentEvent[RecentTrade] = await self._recent_trades_queue.get()
            recent_trade = item.data

            for ws in self._channels[item.instrument][InstrumentEventType.RECENT_TRADE]:
                await ws.send_text(
                    InstrumentStreamMessage(
                        event_type=InstrumentEventType.RECENT_TRADE,
                        data=recent_trade,
                    ).model_dump_json()
                )

    async def _price_heartbeat(self) -> None:
        while True:
            for hash_key, instrument in self._instruments:
                price = await REDIS_CLIENT.hget(hash_key, instrument)
                price = str(price)

                try:
                    for ws in self._channels[instrument][
                        InstrumentEventType.PRICE_UPDATE
                    ]:
                        await ws.send_text(price)
                except Exception as e:
                    logger.error(
                        f"Error: {type(e)} - {str(e)} - line: {get_exc_line()}"
                    )
