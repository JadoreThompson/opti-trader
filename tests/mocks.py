import asyncio

from datetime import datetime
from enum import Enum
from json import dumps
from uuid import UUID, uuid4

from config import PAYLOAD_PUSHER_QUEUE, REDIS_CLIENT
from engine.orders import OCOOrder


class MockCelery:
    def __init__(self, func) -> None:
        self.func = func
        self.last_call = None

    def delay(self, *args, **kwargs):
        self.func(*args, **kwargs)


class MockOCOManager:
    def __init__(self) -> None:
        self.orders = {}

    def create(self):
        order = OCOOrder(uuid4())
        self.orders[order.id] = order
        return order

    def remove(self, order_id):
        self.orders.pop(order_id, None)

    def get(self, order_id):
        return self.orders.get(order_id)


class MockQueue(asyncio.Queue):
    def __init__(self, maxsize: int = 0) -> None:
        super().__init__(maxsize)
        self._loop = asyncio.get_event_loop()

    def _dump_dict(self, obj: dict):
        for k, v in obj.items():
            if isinstance(v, dict):
                obj[k] = self._dump_dict(v)
            elif isinstance(v, (UUID, datetime)):
                obj[k] = str(v)
            elif isinstance(v, Enum):
                obj[k] = v.value

        return obj

    def append(self, obj: object):
        self._loop.create_task(
            REDIS_CLIENT.publish(PAYLOAD_PUSHER_QUEUE, dumps(self._dump_dict(obj)))
        )
        return self.put_nowait(obj)

    def get(self):
        return self.get_nowait()
