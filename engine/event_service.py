from enums import EventType
from .tasks import log_event
from .typing import Event


class EventService:
    """Centralize event logging"""

    @classmethod
    def log_order_event(cls, event_type: EventType, payload: dict, **kw) -> None:
        event = Event(
            event_type=event_type,
            user_id=payload["user_id"],
            order_id=payload["order_id"],
            **kw
        )
        log_event.delay(event.model_dump())

    @classmethod
    def log_rejection(cls, payload: dict, **kw) -> None:
        ev = Event(
            event_type=EventType.ORDER_REJECTED,
            order_id=payload["order_id"],
            user_id=payload["user_id"],
            **kw
        )
        log_event.delay(ev.model_dump())