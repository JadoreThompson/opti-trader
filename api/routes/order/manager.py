import asyncio
import json

from fastapi import WebSocket
from config import BALANCE_UPDATE_CHANNEL, ORDER_UPDATE_CHANNEL, REDIS_CLIENT
from .enums import SocketPayloadCategory
from .models import OrderRead
from ...utils import ConnectPayload, SocketPayload


class ClientManager:
    def __init__(self) -> None:
        self._is_running: bool = False
        self._connections: dict[str, WebSocket] = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()

        if not self._is_running:
            asyncio.create_task(self.listen_to_order_updates())
            asyncio.create_task(self.listen_to_balance_updates())
            self._is_running = True

    def disconnect(self, user_id: str) -> None:
        self._connections.pop(user_id, None)

    def append(self, ws: WebSocket, user_id: str):
        self._connections[user_id] = ws

    async def listen_to_order_updates(self) -> None:
        async with REDIS_CLIENT.pubsub() as ps:
            await ps.subscribe(ORDER_UPDATE_CHANNEL)
            async for message in ps.listen():
                if message["type"] == "subscribe":
                    continue
                asyncio.create_task(
                    self._handle_order_updates(json.loads(message["data"]))
                )

    async def _handle_order_updates(self, payload: dict) -> None:
        ws = self._connections.get(payload["user_id"])
        if ws is not None:
            await ws.send_text(
                json.dumps(
                    SocketPayload(
                        category=SocketPayloadCategory.ORDER,
                        content=OrderRead(**payload).model_dump(),
                    ).model_dump()
                )
            )

    async def listen_to_balance_updates(self) -> None:
        async with REDIS_CLIENT.pubsub() as ps:
            await ps.subscribe(BALANCE_UPDATE_CHANNEL)
            async for message in ps.listen():
                if message["type"] == "subscribe":
                    continue

                asyncio.create_task(
                    self._handle_balance_updates(json.loads(message["data"]))
                )

    async def _handle_balance_updates(self, payload: dict) -> None:
        ws = self._connections.get(payload["user_id"])
        if ws is not None:
            del payload["user_id"]
            await ws.send_text(
                json.dumps(
                    SocketPayload(
                        category=SocketPayloadCategory.BALANCE,
                        content=payload,
                    ).model_dump()
                )
            )

    @property
    def is_running(self) -> bool:
        return self._is_running
