import asyncio
from json import loads

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from pydantic import ValidationError

from .managers import InstrumentManager, OrderManager
from .models import SubscribeRequest


route = APIRouter(prefix="/ws", tags=["websockets"])
instrument_manager = InstrumentManager()
order_manager = OrderManager()
HEARTBEAT_SECONDS = 5


@route.websocket("/instruments")
async def websocket_live_prices(ws: WebSocket):
    """Public websocket for live price, trades and orderbook."""
    global instrument_manager

    await ws.accept()
    close_reason = None

    try:
        while True:
            m = asyncio.wait_for(ws.receive_text, timeout=HEARTBEAT_SECONDS)
            parsed_m = SubscribeRequest(**loads(m))

            if parsed_m.type == "subscribe":
                instrument_manager.subscribe(parsed_m.channel, parsed_m.instrument, ws)
            else:
                instrument_manager.unsubscribe(
                    parsed_m.channel, parsed_m.instrument, ws
                )

    except ValidationError:
        close_reason = "Invalid payload"
    except asyncio.TimeoutError:
        close_reason = "Heartbeat timeout"
    except (RuntimeError, WebSocketDisconnect):
        pass
    finally:
        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close(reason=close_reason)


@route.websocket("/orders")
async def websocket_orders(ws: WebSocket):
    global order_manager

    print(ws.headers)

    await ws.accept()
    close_reason = None

    try:
        while True:
            asyncio.wait_for(ws.receive_text, timeout=HEARTBEAT_SECONDS)

    except asyncio.TimeoutError:
        close_reason = "Heartbeat timeout"
    except (RuntimeError, WebSocketDisconnect):
        pass
    finally:
        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close(reason=close_reason)
