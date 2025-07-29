from json import loads
from fastapi import WebSocket
from fastapi.websockets import WebSocketState

from config import REDIS_CLIENT
from models import ClientEvent


class ClientManger:
    def __init__(self):
        self._listeners: dict[str, WebSocket] = {}
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    async def run(self) -> None:
        if not self._is_running:
            await self._listen()

    async def _listen(self) -> None:
        async with REDIS_CLIENT.pubsub() as ps:
            await ps.subscribe("live-updates")
            async for m in ps.listen():
                if m["type"] == "subscribe":
                    self._is_running = True
                    continue

                parsed_m = ClientEvent(**loads(m["data"]))
                if parsed_m.user_id in self._listeners:
                    await self._listeners[parsed_m.user_id].send_bytes(
                        parsed_m.model_dump_json()
                    )

    async def append(self, user_id: str, ws: WebSocket) -> None:
        if user_id in self._listeners:
            existing_ws = self._listeners[user_id]
            if existing_ws.client_state != WebSocketState.DISCONNECTED:
                await existing_ws.close()

        self._listeners[user_id] = ws

    def remove(self, user_id: str) -> None:
        self._listeners.pop(user_id, None)
