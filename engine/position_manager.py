from engine.order import Order
from .position import Position


class PositionManager:
    def __init__(self) -> None:
        self._positions: dict[str, Position] = {}

    def create(self, order: Order) -> Position:
        if order.tag != "ENTRY":
            raise ValueError("Order must be of type ENTRY to create a Position.")
        pos = Position(order)
        self._positions[order.payload["order_id"]] = pos
        return pos

    def get(self, order_id: str) -> Position | None:
        return self._positions.get(order_id)