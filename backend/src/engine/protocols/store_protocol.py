from typing import Any, Generic, Protocol, TypeVar


T = TypeVar("T")


class StoreProtocol(Protocol, Generic[T]):
    def add(self, value: T) -> None: ...

    def remove(self, value: T) -> T | None: ...

    def get(self, value: Any) -> None: ...
