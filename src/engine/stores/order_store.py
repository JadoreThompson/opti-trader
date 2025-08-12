from ..orders import Order
from ..protocols import StoreProtocol


class OrderStore(StoreProtocol[Order]):
    def __init__(self):
        self._orders: dict[str, Order] = {}

    def add(self, value: Order) -> None:
        self._orders.setdefault(value.id, value)

    def remove(self, value: Order) -> None:
        self._orders.pop(value.id, None)

    def get(self, value: str) -> Order | None:
        return self._orders.get(value)
