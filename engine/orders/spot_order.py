from enums import Side
from .order import Order
from ..enums import Tag


class SpotOrder(Order):
    def __init__(
        self,
        id_,
        tag: Tag,
        side: Side,
        quantity: int,
        price: float = None,
        *,
        oco_id: str = None
    ) -> None:
        super().__init__(id_, tag, side, quantity, price)
        self._oco_id = oco_id

    @property
    def oco_id(self) -> str | None:
        return self._oco_id

    def set_oco_id(self, oco_id: str) -> None:
        if self._oco_id is None:
            self._oco_id = oco_id
