from starlette.websockets import WebSocketDisconnect
from fastapi import APIRouter, WebSocket

# Local
from engine.client_manager import ClientManager

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
    manager = ClientManager(websocket)
    try:
        await manager.connect()
        await manager.receive()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print("[STREAM TRADE][ERROR] >> ", type(e), str(e))
