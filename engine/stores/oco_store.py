from ..protocols import StoreProtocol
from ..orders import Order, OCOOrder


class OCOOrderStore(StoreProtocol):
    def __init__(self):
        self._orders: dict[str, OCOOrder] = {}

    def add(self, value: Order) -> None:
        if value.id in self._orders:
            raise ValueError(f"Order with ID {value.id} already exists.")

        # self._orders[value.id] = OCOOrder(id_=value.id, tag=)

    def get(self, value: str) -> OCOOrder | None:
        return self._orders.get(value)

    def remove(self, value: OCOOrder) -> None:
        self._orders.pop(value.id, None)
