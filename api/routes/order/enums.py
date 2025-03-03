from enum import Enum


class SocketPayloadCategory(str, Enum):
    CONNECT = 'connect',
    PRICE = 'price',
    ORDER = 'order',