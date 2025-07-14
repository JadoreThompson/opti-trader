from typing import Generic, Type, TypeVar
from engine.base_position import BasePosition
from enums import OrderStatus

T = TypeVar("T", bound=BasePosition)


class PositionManager(Generic[T]):
    def __init__(self, position_cls: Type[T]) -> None:
        self._position_cls = position_cls
        self._positions: dict[str, T] = {}

    def create(self, payload: dict) -> T:
        if payload["status"] != OrderStatus.PENDING:
            raise ValueError("Payload must be a newly created pending payload.")

        if payload["order_id"] in self._positions:
            raise ValueError(f"Payload with id {payload["order_id"]} already exists.")

        pos = self._position_cls(payload)
        self._positions[payload["order_id"]] = pos
        return pos

    def get(self, order_id: str) -> T | None:
        return self._positions.get(order_id)

    def remove(self, order_id: str) -> None:
        self._positions.pop(order_id)
