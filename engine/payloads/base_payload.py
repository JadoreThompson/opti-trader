from enums import OrderStatus


class BasePayload:
    def __init__(self, payload: dict):
        self._payload = payload
        self._filled_volume: float = 0.0

    @property
    def payload(self) -> dict:
        return self._payload

    def apply_fill(self, quantity: int, price: float) -> None:
        if quantity <= 0:
            return

        self._payload["open_quantity"] += quantity
        self._payload["standing_quantity"] -= quantity

        self._filled_volume += quantity * price
        self._payload["filled_price"] = (
            self._filled_volume / self.payload["open_quantity"]
        )

        if self._payload["standing_quantity"] == 0:
            self._payload["status"] = OrderStatus.FILLED
        else:
            self._payload["status"] = OrderStatus.PARTIALLY_FILLED

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(status={self._payload.get('status')}, open_quantity={self._payload.get('open_quantity')}, standing_quantity={self._payload.get('standing_quantity')}, filled_price={self._payload.get('filled_price')}, filled_volume={self._filled_volume})"

    def __str__(self):
        return self.__repr__()
