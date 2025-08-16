from pydantic import BaseModel, Field

from enums import EventType, StrategyType
from models import CustomBaseModel
from .enums import CommandType


MODIFY_SENTINEL = "*"


class Command(CustomBaseModel):
    command_type: CommandType
    data: CustomBaseModel


class NewOrderCommand(CustomBaseModel):
    strategy_type: StrategyType
    instrument_id: str  # From DB


class NewSingleOrder(NewOrderCommand):
    order: dict


class NewOCOOrder(NewOrderCommand):
    legs: list[dict] = Field(max_length=2)


class NewOTOOrder(NewOrderCommand):
    parent: dict
    child: dict


class NewOTOCOOrder(NewOrderCommand):
    parent: dict
    oco_legs: list[dict] = Field(max_length=2)


class CancelOrderCommand(CustomBaseModel):
    order_id: str
    symbol: str


class ModifyOrderCommand(CustomBaseModel):
    order_id: str
    symbol: str
    limit_price: float = MODIFY_SENTINEL
    stop_price: float = MODIFY_SENTINEL


class NewInstrument(CustomBaseModel):
    instrument_id: str


class Event(CustomBaseModel):
    event_type: EventType
    user_id: str
    related_id: str
    instrument_id: str
    details: dict | None = None
