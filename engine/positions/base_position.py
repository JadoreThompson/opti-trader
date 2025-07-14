from engine.orders.order import Order


class BasePosition:
    def __init__(
        self,
        payload: dict,
        entry_order: Order | None = None,
        take_profit_order: Order | None = None,
        stop_loss_order: Order | None = None,
    ):
        self._payload = payload
        self.entry_order = entry_order
        self.stop_loss_order = stop_loss_order
        self.take_profit_order = take_profit_order

    @property
    def id(self) -> int:
        return self._payload["order_id"]

    @property
    def instrument(self) -> str:
        return self._payload["instrument"]

    @property
    def status(self):
        return self._payload["status"]

    @property
    def payload(self) -> dict:
        """Returns the current state payload."""
        return self._payload

    @property
    def open_quantity(self) -> int:
        return self._payload["open_quantity"]

    @property
    def standing_quantity(self) -> int:
        return self._payload["standing_quantity"]
