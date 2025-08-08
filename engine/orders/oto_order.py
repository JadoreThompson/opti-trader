from .order import Order


class OTOOrder(Order):
    def __init__(
        self,
        id_,
        typ,
        tag,
        side,
        quantity,
        price=None,
        *,
        is_worker: bool,
        counterparty: Order | None = None
    ) -> None:
        super().__init__(id_, typ, tag, side, quantity, price)
        self.counterparty = counterparty
        self._is_worker = is_worker

    @property
    def is_worker(self) -> bool:
        return self._is_worker
