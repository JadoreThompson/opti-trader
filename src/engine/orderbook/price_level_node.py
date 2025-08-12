from __future__ import annotations

from ..orders import Order


class PriceLevelNode:
    """
    Doubly linked list to house an order within
    a PriceLevel.
    """

    def __init__(
        self,
        order: Order,
        prev: PriceLevelNode | None = None,
        next: PriceLevelNode | None = None,
    ):
        self.order = order
        self.prev = prev
        self.next = next
