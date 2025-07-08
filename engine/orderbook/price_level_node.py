from __future__ import annotations
from ..order import Order


class PriceLevelNode:
    def __init__(
        self,
        order: Order,
        prev: PriceLevelNode | None = None,
        next: PriceLevelNode | None = None,
    ):
        self.order = order
        self.prev = prev
        self.next = next
