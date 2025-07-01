import asyncio
import json

from collections import defaultdict
from datetime import datetime
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from config import REDIS_CLIENT
from .models import PricePayload
from ...utils import SocketPayload, SocketPayloadCategory, handle_ws_errors


class ClientManager:
    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, ws: WebSocket, instrument: str) -> None:
        await ws.accept()

        if instrument not in self._connections:
            asyncio.create_task(self.listen_to_price(instrument))

        self._connections[instrument].append(ws)

    def disconnect(self, ws: WebSocket, instrument: str) -> None:
        if ws in self._connections.get(instrument, []):
            self._connections[instrument].remove(ws)

    async def listen_to_price(self, instrument: str) -> None:
        last_push = None

        async with REDIS_CLIENT.pubsub() as ps:
            await ps.subscribe(f"{instrument}.live")
            async for message in ps.listen():
                if message["type"] == "subscribe":
                    continue

                if last_push is not None:
                    await asyncio.sleep(
                        max(0, 60 - (datetime.now().timestamp() - last_push))
                    )
                
                await self._handle_price(message["data"].decode(), instrument)
                last_push = datetime.now().timestamp()

    @handle_ws_errors
    async def _handle_price(self, price: float, instrument: str) -> None:
        payload = json.dumps(
            SocketPayload(
                category=SocketPayloadCategory.PRICE,
                content=PricePayload(
                    price=price, time=int(datetime.now().timestamp())
                ).model_dump(),
            ).model_dump()
        )

        for ws in self._connections[instrument]:
            try:
                await ws.send_text(payload)
            except WebSocketDisconnect:
                self.disconnect(ws, instrument)
