import asyncio
import json

from datetime import datetime
from typing import TypedDict
from fastapi import WebSocket

from config import BALANCE_UPDATE_CHANNEL, ORDER_UPDATE_CHANNEL, REDIS_CLIENT
from .enums import SocketPayloadCategory
from .models import ConnectPayload, OrderRead, PricePayload, SocketPayload


class ConnectionDetails(TypedDict):
    instrument: str
    websocket: WebSocket


class ClientManager:
    def __init__(self) -> None:
        self._is_running: bool = False
        self._connections: dict[str, ConnectionDetails] = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()

        if not self._is_running:
            asyncio.create_task(self.listen_to_price())
            asyncio.create_task(self.listen_to_order_updates())
            asyncio.create_task(self.listen_to_balance_updates())
            self._is_running = True

    async def disconnect(self, user_id: str) -> None:
        self._connections.pop(user_id, None)

    async def append(self, ws: WebSocket, user_id: str, payload: ConnectPayload):
        self._connections[user_id] = {
            "instrument": payload["instrument"],
            "websocket": ws,
        }

    async def listen_to_price(self) -> None:
        instrument = "BTCUSD"
        async with REDIS_CLIENT.pubsub() as ps:
            await ps.subscribe(f"{instrument}.live")
            async for message in ps.listen():
                if message["type"] == "subscribe":
                    continue
                asyncio.create_task(
                    self._handle_price(message["data"].decode(), instrument)
                )

    async def _handle_price(self, price: float, instrument: str) -> None:
        payload = json.dumps(
            SocketPayload(
                category=SocketPayloadCategory.PRICE,
                content=PricePayload(
                    price=price, time=int(datetime.now().timestamp())
                ).model_dump(),
            ).model_dump()
        )

        for _, details in self._connections.items():
            if details["instrument"] == instrument:
                await details["websocket"].send_text(payload)

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
        ws = self._connections.get(payload["user_id"], {}).get("websocket")
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
        ws = self._connections.get(payload["user_id"], {}).get("websocket")
        if ws is not None:
            del payload['user_id']
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
