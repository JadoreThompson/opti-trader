from __future__ import annotations
from .order import Order


class OTOCOOrder(Order):
    def __init__(
        self,
        id_,
        typ,
        tag,
        side,
        quantity,
        price=None,
        *,
        is_trigger: bool,
        trigger_order: OTOCOOrder | None = None,
        above_order: OTOCOOrder | None = None,
        below_order: OTOCOOrder | None = None,
    ):
        super().__init__(id_, typ, tag, side, quantity, price)
        self._trigger_order = trigger_order
        self.above_order = above_order
        self.below_order = below_order
        self._is_trigger = is_trigger

    @property
    def is_trigger(self) -> bool:
        return self._is_trigger

    @property
    def trigger_order(self) -> OTOCOOrder:
        return self._trigger_order
