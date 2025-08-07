from .order import Order


class OTOOrder(Order):
    def __init__(
        self,
        db_id,
        id_,
        tag,
        side,
        price,
        quantity,
        *,
        counterparty: Order | None = None
    ):
        super().__init__(db_id, id_, tag, side, price, quantity)
        self.counterparty = counterparty
