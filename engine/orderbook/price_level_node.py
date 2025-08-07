from typing import Self
from ..orders.order import Order


class PriceLevelNode:
    """
    Doubly linked list to house an order within
    a PriceLevel.
    """

    def __init__(
        self,
        order: Order,
        prev: Self | None = None,
        next: Self | None = None,
    ):
        self.order = order
        self.prev = prev
        self.next = next
