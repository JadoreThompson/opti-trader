from ..protocols import StoreProtocol
from ..orders import Order


class OrderStore(StoreProtocol):
    def __init__(self):
        self._orders: dict[str, Order] = {}

    def add(self, value: Order) -> None:
        if value.id in self._orders:
            raise ValueError(f"Order with ID {value.id} already exists.")

        self._orders[value.id] = value

    def get(self, value: str) -> Order | None:
        return self._orders.get(value)

    def remove(self, value: Order) -> None:
        self._orders.pop(value.id, None)
