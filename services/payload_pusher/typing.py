from enum import Enum
from pydantic import BaseModel
from sqlalchemy import insert, update
from typing import Union


class PusherPayloadTopic(Enum):
    INSERT = 0
    UPDATE = 1


class PusherPayload(BaseModel):
    action: PusherPayloadTopic
    table_cls: str
    data: dict


MutationFunc = Union[insert, update]
