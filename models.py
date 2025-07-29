from pydantic import BaseModel
from engine.typing import EventType


class ClientEvent(BaseModel):
    event_type: EventType
    user_id: str
    order_id: str