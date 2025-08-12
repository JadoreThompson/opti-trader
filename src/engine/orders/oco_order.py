from __future__ import annotations

from .order import Order


class OCOOrder(Order):
    def __init__(
        self,
        id_,
        user_id,
        strategy_type,
        order_type,
        side,
        quantity,
        price=None,
        *,
        counterparty: OCOOrder | None = None,
    ):
        super().__init__(id_, user_id, strategy_type, order_type, side, quantity, price)
        self.counterparty = counterparty
