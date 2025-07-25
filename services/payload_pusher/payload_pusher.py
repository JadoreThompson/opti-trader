import asyncio
import json
import logging

from collections import defaultdict, deque
from datetime import datetime
from sqlalchemy import insert, update
from typing import Type, get_args, get_origin
from types import UnionType

import db_models
from config import PAYLOAD_PUSHER_QUEUE, REDIS_CLIENT
from utils.db import get_db_session
from utils.utils import get_exc_line
from .typing import PusherPayload, PusherPayloadTopic, MutationFunc

logger = logging.getLogger(__name__)


class PayloadPusher:
    """Listens for payloads from Redis and periodically pushes them to the database."""

    def __init__(self, interval: int = 1) -> None:
        """
        Args:
            interval (int, optional): How often records need to be
                sent to DB in seconds. Defaults to 1.
        """
        self._tables: dict[str, Type[db_models.Base]] = {
            key: val
            for key, val in db_models.__dict__.items()
            if isinstance(val, type)
            and issubclass(val, db_models.Base)
            and val is not db_models.Base
        }
        self._interval = interval
        self._queue = defaultdict(lambda: defaultdict(deque))
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if asyncio.get_event_loop().is_running():
            await asyncio.gather(self._listen(), self._push())

    async def _listen(self) -> None:
        """Continuously listen to the Redis pub/sub channel and queue payloads."""
        async with REDIS_CLIENT.pubsub() as ps:
            await ps.subscribe(PAYLOAD_PUSHER_QUEUE)
            async for m in ps.listen():
                if m["type"] == "subscribe":
                    continue

                try:
                    msg = PusherPayload(**json.loads(m["data"]))
                    async with self._lock:
                        self._queue[msg.table_cls][msg.action].append(msg.data)
                except Exception as e:
                    logger.error(
                        f"Error: {type(e)} - {str(e)} - line: {get_exc_line()}"
                    )

    async def _push(self) -> None:
        """Periodically flush queued payloads to the database."""
        while True:
            coroutines = []

            async with self._lock:
                for table_cls_name in self._queue:
                    for action, records in self._queue[table_cls_name].items():
                        if records:
                            coroutines.append(
                                self._mutate(
                                    (
                                        insert
                                        if action == PusherPayloadTopic.INSERT
                                        else update
                                    ),
                                    self._tables[table_cls_name],
                                    [*records],
                                )
                            )
                            records.clear()

            if coroutines:
                await asyncio.gather(*coroutines)

            await asyncio.sleep(self._interval)

    async def _mutate(
        self, mfunc: MutationFunc, table_cls: Type, records: list[dict]
    ) -> None:
        """Execute a mutation on the database.

        Args:
            mfunc (MutationFunc): SQLAlchemy insert or update function.
            table_cls (Type): Target SQLAlchemy model class.
            records (list[dict]): List of records to insert or update.
        """
        table_annotations = table_cls.__annotations__.items()

        for rec in records:            
            for field, field_typ in table_annotations:
                val = rec.get(field)
                if val is None:
                    continue

                typ = get_args(field_typ)[0]

                if (origin := get_origin(typ)) is not None and issubclass(
                    origin, UnionType
                ):
                    typ = get_args(typ)[0]

                if not isinstance(val, typ):
                    if typ == datetime:
                        rec[field] = datetime.fromisoformat(val)
                    else:
                        rec[field] = typ(val)
                
        try:
            async with get_db_session() as sess:
                await sess.execute(mfunc(table_cls), records)
                await sess.commit()
        except Exception as e:
            logger.error(f"Error: {type(e)} - {str(e)} - line: {get_exc_line()}")
