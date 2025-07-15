from uuid import uuid4
from .orders import OCOOrder


class OCOManager:
    def __init__(self) -> None:
        self._orders: dict[str, OCOOrder] = {}

    def create(self) -> OCOOrder:
        oco_id = uuid4()
        oco_order = self._orders.setdefault(oco_id, OCOOrder(oco_id))
        return oco_order

    def get(self, oco_id: str) -> OCOOrder | None:
        return self._orders.get(oco_id)

    def remove(self, oco_id: str) -> None:
        return self._orders.pop(oco_id, None)
