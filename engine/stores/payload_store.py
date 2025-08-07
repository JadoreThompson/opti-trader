from typing import Generic, TypeVar
from ..protocols import StoreProtocol, PayloadProtocol


T = TypeVar("T", bound=PayloadProtocol)


class PayloadStore(StoreProtocol, Generic[T]):
    def __init__(self):
        self._payloads: dict[str, T] = {}

    def add(self, value: T) -> None:
        db_payload = value.payload
        if db_payload["order_id"] in self._payloads:
            raise ValueError(
                f"DB Payload with ID {db_payload['order_id']} already exists."
            )

        self._payloads[db_payload["order_id"]] = value

    def get(self, value: str) -> T | None:
        return self._payloads.get(value)

    def remove(self, value: T) -> None:
        self._payloads.pop(value.payload["order_id"])
