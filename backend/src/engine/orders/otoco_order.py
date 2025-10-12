from __future__ import annotations

from enums import OrderType, Side, StrategyType
from .order import Order


class OTOCOOrder(Order):
    def __init__(
        self,
        id_: str,
        user_id: str,
        strategy_type: StrategyType,
        order_type: OrderType,
        side: Side,
        quantity: int,
        price: float,
        *,
        parent: OTOCOOrder | None = None,
        child_a: OTOCOOrder | None = None,
        child_b: OTOCOOrder | None = None,
        counterparty: OTOCOOrder | None = None, # For OCO
    ):
        super().__init__(id_, user_id, strategy_type, order_type, side, quantity, price)
        self.parent = parent
        self.child_a = child_a
        self.child_b = child_b
        self.counterparty = counterparty
        # The parent order is triggered by default; children are not.
        self.triggered = parent is None
