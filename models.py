from pydantic import BaseModel
from enums import ClientEventType, EventType, MarketType


class ClientEvent(BaseModel):
    event_type: ClientEventType | EventType
    user_id: str
    order_id: str
    data: dict

class PriceUpdate(BaseModel):
    instrument: str
    price: float
    market_type: MarketType