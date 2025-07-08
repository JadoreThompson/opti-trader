from .price_level_node import PriceLevelNode
from ..order import Order


class PriceLevel:
    def __init__(self) -> None:
        self.head: PriceLevelNode | None = None
        self.tail: PriceLevelNode | None = None
        self.tracker: dict[str, PriceLevelNode] = {}

    def append(self, order: Order) -> None:
        if order.payload["order_id"] in self.tracker:
            raise ValueError(
                f"Order with id {order.payload['order_id']} already on level."
            )

        new_node = PriceLevelNode(order)

        if self.head is None:
            self.head = new_node
            self.tail = new_node
        else:
            self.tail.next = new_node
            new_node.prev = self.tail
            self.tail = new_node

        self.tracker[order.payload["order_id"]] = new_node

    def remove(self, order: Order) -> None:
        orders_node = self.tracker[order.payload["order_id"]]

        if orders_node.prev is not None:
            orders_node.prev.next = orders_node.next

        if orders_node.next is not None:
            orders_node.next.prev = orders_node.prev

        if self.head == orders_node:
            self.head = orders_node.next

        if self.tail == orders_node:
            self.tail = orders_node.prev

        # Cleanup
        orders_node.prev = None
        orders_node.next = None
        self.tracker.pop(order.payload["order_id"])

    def __bool__(self):
        return self.head is not None
