import json, asyncio
from starlette.websockets import WebSocketDisconnect
from fastapi import APIRouter, WebSocket

# Local
from engine.client_manager import ClientManager


MANAGER = ClientManager()
stream = APIRouter(prefix='/stream', tags=['stream'])


@stream.websocket("/trade")
async def trade(websocket: WebSocket):
    """
    Handles WebSocket connections for trade streaming.
    Args:
        websocket (WebSocket): The WebSocket connection instance.
    Raises:
        Exception: For any error encountered during WebSocket acceptance.
    """
    user_id = None
    try:
        # Auth
        await MANAGER.connect(websocket)
        
        user_id = await MANAGER.receive_token(websocket)
        if not user_id:
            await websocket.close(code=1014, reason="Invalid token")
            
        # Receive
        while True:
            await MANAGER.receive(websocket, user_id)
            await asyncio.sleep(0.1)
            
    except WebSocketDisconnect as e:
        await MANAGER.cleanup(user_id)
    except Exception as e:
        print("[TRADE STREAM ENDPOINT][ERROR] >> ", type(e), str(e))
