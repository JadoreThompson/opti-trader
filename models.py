from pydantic import BaseModel
from enums import ClientEventType, EventType


class ClientEvent(BaseModel):
    event_type: ClientEventType | EventType
    user_id: str
    order_id: str
    data: dict
