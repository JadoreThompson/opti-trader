from typing import Protocol


class PayloadProtocol(Protocol):
    @property
    def payload(self) -> dict: ...

    def apply_fill(self, quantity: int, price: float) -> None: ...
