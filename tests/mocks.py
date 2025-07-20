from uuid import uuid4
from engine.orders import OCOOrder


class MockCelery:
    def __init__(self, func) -> None:
        self.func = func
        self.last_call = None

    def delay(self, *args, **kwargs):
        self.func(*args, **kwargs)


class MockOCOManager:
    def __init__(self) -> None:
        self.orders = {}

    def create(self):
        order = OCOOrder(uuid4())
        self.orders[order.id] = order
        return order

    def remove(self, order_id):
        self.orders.pop(order_id, None)

    def get(self, order_id):
        return self.orders.get(order_id)
