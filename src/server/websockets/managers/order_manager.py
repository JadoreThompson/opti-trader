import asyncio
from json import loads

from fastapi import WebSocket
from fastapi.websockets import WebSocketState

from config import ORDER_UPDATE_QUEUE, REDIS_CLIENT_ASYNC
from models import OrderUpdate, PriceUpdate


class OrderManager:
    def __init__(self):
        self._channels: dict[str, WebSocket] = {}

    @property
    def is_running(self) -> bool:
        return self._is_running

    async def subscribe(self, user_id: str, ws: WebSocket) -> None:
        if (
            user_id in self._channels
            and self._channels[user_id].client_state != WebSocketState.DISCONNECTED
        ):
            await self._channels[user_id].close()

        self._channels[user_id] = ws

    def unsubscribe(self, user_id: str) -> None:
        self._channels.pop(user_id, None)

    async def listen(self):
        async with REDIS_CLIENT_ASYNC.pubsub() as ps:
            await ps.subscribe(ORDER_UPDATE_QUEUE)
            async for m in ps.listen():
                if m["type"] == "subscribe":
                    self._is_running = True
                    continue

                parsed_m = OrderUpdate(**loads(m["data"]))

                if parsed_m.user_id in self._channels:
                    await self._channels[parsed_m.user_id].send_json(
                        parsed_m.model_dump_json()
                    )
