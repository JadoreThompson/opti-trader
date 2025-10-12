from multiprocessing.queues import Queue as MPQueue

from enums import EventType
from .models import Event


class EventLogger:
    queue: MPQueue | None = None

    @classmethod
    def log_event(cls, etype: EventType, **kw) -> None:
        ev = Event(event_type=etype, **kw)

        if cls.queue is not None:
            cls.queue.put_nowait(ev)
