from enum import Enum
from typing import Literal
from pydantic import BaseModel

from enums import InstrumentEventType


class SubscribeRequest(BaseModel):
    type: Literal["subscribe", "unsubscribe"]
    channel: InstrumentEventType
