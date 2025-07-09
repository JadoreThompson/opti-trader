from .price_level_node import PriceLevelNode
from ..order import Order


class PriceLevel:
    def __init__(self) -> None:
        self._head: PriceLevelNode | None = None
        self._tail: PriceLevelNode | None = None
        self._tracker: dict[str, PriceLevelNode] = {}

    def append(self, order: Order) -> None:
        if order.payload["order_id"] in self._tracker:
            raise ValueError(
                f"Order with id {order.payload['order_id']} already on level."
            )

        new_node = PriceLevelNode(order)

        if self._head is None:
            self._head = new_node
            self._tail = new_node
        else:
            self._tail.next = new_node
            new_node.prev = self._tail
            self._tail = new_node

        self._tracker[order.payload["order_id"]] = new_node

    def remove(self, order: Order) -> None:
        orders_node = self._tracker[order.payload["order_id"]]

        if orders_node.prev is not None:
            orders_node.prev.next = orders_node.next

        if orders_node.next is not None:
            orders_node.next.prev = orders_node.prev

        if self._head == orders_node:
            self._head = orders_node.next

        if self._tail == orders_node:
            self._tail = orders_node.prev

        # Cleanup
        orders_node.prev = None
        orders_node.next = None
        self._tracker.pop(order.payload["order_id"])

    def __bool__(self):
        return self._head is not None

    @property
    def head(self) -> PriceLevelNode | None:
        return self._head

    @property
    def tail(self) -> PriceLevelNode | None:
        return self._tail

    @property
    def tracker(self) -> dict[str, PriceLevelNode]:
        return self._tracker
