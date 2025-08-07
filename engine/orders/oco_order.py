from __future__ import annotations
from .order import Order


class OCOOrder(Order):
    def __init__(
        self,
        id_,
        typ,
        tag,
        side,
        quantity,
        price=None,
        *,
        is_above: bool,
        counterparty: OCOOrder | None = None,
    ):
        super().__init__(id_, typ, tag, side, quantity, price)
        self.counterparty = counterparty
        self.is_above = is_above
