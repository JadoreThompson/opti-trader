from enum import Enum
from typing import Literal
from pydantic import BaseModel


class InstrumentChannel(Enum):
    PRICE = "price"
    TRADES = "trades"
    ORDERBOOK = "orderbook"


class SubscribeRequest(BaseModel):
    type: Literal['subscribe', 'unsubscribe']
    channel: InstrumentChannel
    instrument: str