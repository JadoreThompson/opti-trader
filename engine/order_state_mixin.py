class OrderStateMixin:
    def apply_fill(self, quantity: int):
        if quantity <= 0:
            raise RuntimeError()

        self._payload["standing_quantity"] -= quantity
        self._payload["open_quantity"] += quantity

    def apply_close(self, quantity: int):
        self._payload["open_quantity"] -= quantity
