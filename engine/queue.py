from datetime import datetime
from enum import Enum
from multiprocessing import Queue as MPQueue
from uuid import UUID


class Queue:
    def __init__(self):
        self._queue = MPQueue()

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
        if isinstance(obj, dict):
            obj = self._dump_dict(obj)
        return self._queue.put(obj)

    def get(self, *args, **kwargs):
        return self._queue.get(*args, **kwargs)

    def size(self):
        return self._queue.qsize()