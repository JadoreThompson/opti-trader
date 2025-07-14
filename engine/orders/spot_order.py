from pydantic import Tag
from engine.order_state_mixin import OrderStateMixin
from enums import Side
from .order import Order


class SpotOrder(OrderStateMixin, Order):
    def __init__(
        self,
        id_,
        tag: Tag,
        side: Side,
        quantity: int,
        price: float = None,
        *,
        payload: dict
    ) -> None:
        super().__init__(id_, tag, side, quantity, price)
        self._payload = payload

    @property
    def payload(self):
        return self._payload
