import asyncio
from typing import Literal
from sqlalchemy import update
from db_models import Orders
from utils.db import get_db_session


class Pusher:
    def __init__(self, delay: float = 2) -> None:
        "Delay in seconds"
        self._collection: list[dict] = []
        self._delay = delay
        self._is_running: bool = False

    async def run(self) -> None:
        self._is_running = True
        print("[pusher] Pusher Running")
        while True:
            if self._collection:
                try:
                    async with get_db_session() as sess:
                        await sess.execute(update(Orders), self._collection)
                        await sess.commit()
                    self._collection.clear()
                except Exception as e:
                    print(
                        f"[pusher][run] => Error: type - ",
                        type(e),
                        "content - ",
                        str(e),
                    )
            await asyncio.sleep(self._delay)

    def append(
        self, obj: dict | list[dict], mode: Literal["lazy", "fast"] = "lazy"
    ) -> None:
        if mode == "lazy":
            if isinstance(obj, list):
                self._collection.extend(obj)
            else:
                self._collection.append(obj)
        else:
            asyncio.get_running_loop().create_task(self._push_fast(obj))

    async def _push_fast(self, obj: dict) -> None:
        async with get_db_session() as sess:
            await sess.execute(update(Orders), [obj])

    @property
    def is_running(self) -> bool:
        return self._is_running
