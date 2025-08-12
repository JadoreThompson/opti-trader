from __future__ import annotations

from enums import OrderType, Side, StrategyType
from .order import Order


class OTOOrder(Order):
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
        parent: OTOOrder | None = None,
        child: OTOOrder | None = None,
    ):
        super().__init__(id_, user_id, strategy_type, order_type, side, quantity, price)
        self.parent = parent
        self.child = child
        # The parent order is triggered by default; the child is not.
        self.triggered = parent is None
