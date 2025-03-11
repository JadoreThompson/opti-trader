from enum import Enum
from typing import Callable
from starlette.websockets import WebSocketDisconnect
from .base import CustomBase


class SocketPayloadCategory(str, Enum):
    CONNECT = 'connect'
    PRICE = 'price'
    ORDER = 'order'
    BALANCE = 'balance'
    

class SocketPayload(CustomBase):
    """Used for both posting and receiving messages"""
    category: SocketPayloadCategory
    content: dict


class ConnectPayload(CustomBase):
    instrument: str


def handle_ws_errors(func: Callable) -> None:
    """
    A decorator used to pass the common exceptions raised
    on client disconnect and other ws actions
    
    Args:
        func (Callable)
    """
    async def _handler(*args, **kwargs) -> None:
        try:
            return await func(*args, **kwargs)
        except WebSocketDisconnect:
            pass
    return _handler