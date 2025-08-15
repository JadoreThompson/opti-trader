import asyncio
from json import loads

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from pydantic import ValidationError

from enums import InstrumentEventType
from server.exc import JWTError
from server.utils.auth import decode_jwt_token, validate_jwt_payload
from .managers import InstrumentManager, OrderManager
from .models import SubscribeRequest


route = APIRouter(prefix="/ws", tags=["websockets"])
instrument_manager = InstrumentManager()
order_manager = OrderManager()
HEARTBEAT_SECONDS = 5


@route.websocket("/instruments/{instrument}")
async def websocket_live_prices(instrument: str, ws: WebSocket):
    """Public websocket for live price, trades and orderbook."""
    global instrument_manager

    await ws.accept()
    close_reason = None

    try:
        while True:
            m = await asyncio.wait_for(ws.receive_text(), timeout=HEARTBEAT_SECONDS)
            if m == "ping":
                continue

            parsed_m = SubscribeRequest(**loads(m))

            if parsed_m.type == "subscribe":
                instrument_manager.subscribe(parsed_m.channel, instrument, ws)
            else:
                instrument_manager.unsubscribe(parsed_m.channel, instrument, ws)

    except ValidationError:
        close_reason = "Invalid payload"
    except asyncio.TimeoutError:
        close_reason = "Heartbeat timeout"
    except (RuntimeError, WebSocketDisconnect):
        pass
    finally:
        instrument_manager.unsubscribe(InstrumentEventType.ORDERBOOK, instrument, ws)
        instrument_manager.unsubscribe(InstrumentEventType.PRICE, instrument, ws)
        instrument_manager.unsubscribe(InstrumentEventType.TRADES, instrument, ws)
        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close(reason=close_reason)


@route.websocket("/orders")
async def websocket_orders(ws: WebSocket):
    global order_manager
    
    await ws.accept()
    close_reason = None
    jwt = None

    try:
        if not order_manager.is_running:
            asyncio.create_task(order_manager.listen())
            
        token = await asyncio.wait_for(ws.receive_text(), timeout=HEARTBEAT_SECONDS)
        payload = decode_jwt_token(token)
        jwt = await validate_jwt_payload(payload)
        await order_manager.subscribe(jwt.sub, ws)
        await ws.send_text("connected")

        while True:
            await asyncio.wait_for(ws.receive_text(), timeout=HEARTBEAT_SECONDS)

    except asyncio.TimeoutError:
        close_reason = "Heartbeat timeout"
    except JWTError:
        close_reason = "Invalid token"
    except (RuntimeError, WebSocketDisconnect):
        pass
    finally:
        if jwt is not None:
            order_manager.unsubscribe(jwt.sub)
        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close(reason=close_reason)
