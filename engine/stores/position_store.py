from ..position import Position
from ..protocols import StoreProtocol
from ..orders import Order


class PositionStore(StoreProtocol):
    def __init__(self):
        self._positions: dict[str, Position] = {}

    def add(self, value: Order) -> None:
        if value.id in self._positions:
            raise ValueError(f"Order with ID {value.id} already exists.")

        self._positions[value.id] = Position(value)

    def get(self, value: str) -> Position | None:
        return self._positions.get(value)

    def remove(self, value: Order) -> None:
        pos = self._positions.get(value.id)
        if pos is None:
            return

        if value is pos.entry_order:
            pos.entry_order = None
        else:
            pos.sl_order = None
            pos.tp_order = None
