from asyncio import Task, create_task, sleep
from collections import defaultdict
from json import loads
from logging import getLogger
from fastapi import WebSocket

from config import FUTURES_BOOKS_KEY, PRICE_UPDATE_CHANNEL, REDIS_CLIENT, SPOT_BOOKS_KEY
from enums import MarketType
from models import PriceUpdate
from utils.utils import get_exc_line

logger = getLogger(__name__)


class ClientManager:
    def __init__(self, delay: int = 5):
        self._delay = delay
        self._tasks: dict[str, Task] = {}
        self._listeners: dict[str, list[WebSocket]] = defaultdict(list)
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    async def run(self) -> None:
        if not self._is_running:
            await self._listen()

    async def _listen(self) -> None:
        async with REDIS_CLIENT.pubsub() as ps:
            await ps.subscribe(PRICE_UPDATE_CHANNEL)
            async for m in ps.listen():
                if m["type"] == "subscribe":
                    self._is_running = True
                    continue

                # TODO: UDP Cast instead?
                payload = PriceUpdate(**loads(m["data"]))

                if payload.instrument not in self._tasks:
                    self._tasks[payload.instrument] = create_task(
                        self._heartbeat(
                            payload.instrument,
                            (
                                FUTURES_BOOKS_KEY
                                if payload.market_type == MarketType.FUTURES
                                else SPOT_BOOKS_KEY
                            ),
                        )
                    )

                price = str(payload.price)
                for ws in self._listeners[payload.instrument]:
                    await ws.send_text(price)

    def append(self, instrument: str, ws: WebSocket) -> None:
        self._listeners[instrument].append(ws)

    def remove(self, instrument: str, ws: WebSocket) -> None:
        try:
            self._listeners[instrument].remove(ws)
        except ValueError:
            pass

    async def _heartbeat(self, instrument: str, hash_key: str):
        while True:
            try:
                await sleep(self._delay)

                price = await REDIS_CLIENT.hget(hash_key, instrument)
                price = str(price)
                for ws in self._listeners[instrument]:
                    await ws.send_text(price)
            except Exception as e:
                logger.error(f"Error: {type(e)} - {str(e)} - line: {get_exc_line()}")
