from __future__ import annotations
from ..order import Order


class Node:
    def __init__(
        self, order: Order, prev: Node | None = None, next: Node | None = None
    ):
        self.order = order
        self.prev = prev
        self.next = next
