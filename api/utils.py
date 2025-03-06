from enum import Enum
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
