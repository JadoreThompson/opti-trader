from enums import OrderStatus
from .position import Position


class PositionManager:
    def __init__(self) -> None:
        self._positions: dict[str, Position] = {}

    def create(self, payload: dict) -> Position:
        if payload["status"] != OrderStatus.PENDING:
            raise ValueError("Payload must be a newly created pending payload.")

        if payload["order_id"] in self._positions:
            raise ValueError(f"Payload with id {payload["order_id"]} already exists.")

        pos = Position(payload)
        self._positions[payload["order_id"]] = pos
        return pos

    def get(self, order_id: str) -> Position | None:
        return self._positions.get(order_id)

    def remove(self, order_id: str) -> None:
        self._positions.pop(order_id)
