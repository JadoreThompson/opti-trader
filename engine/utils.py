import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import insert
from config import CELERY
from db_models import OrderEvents
from utils.db import get_db_session_sync
from .typing import EventDict


def dump_obj(obj: dict) -> str:
    """
    Handles the dumping of a dictionary, converting UUID and datetime fields to strings

    Args:
        obj (dict) - Non nested dictionary
    """
    return json.dumps(
        {k: (str(v) if isinstance(v, (UUID, datetime)) else v) for k, v in obj.items()}
    )


@CELERY.task
def log_event(event: EventDict):
    with get_db_session_sync() as sess:
        sess.execute(insert(OrderEvents).values(**event))
        sess.commit()
