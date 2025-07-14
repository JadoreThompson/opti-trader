from engine.orders.order import Order
from engine.positions.base_position import BasePosition
from engine.order_state_mixin import OrderStateMixin


class SpotPosition(OrderStateMixin, BasePosition):
    def __init__(
        self,
        payload: dict,
        entry_order: Order | None = None,
        stop_loss_order: Order | None = None,
        take_profit_order: Order | None = None,
    ) -> None:
        super().__init__(payload, entry_order, stop_loss_order, take_profit_order)
