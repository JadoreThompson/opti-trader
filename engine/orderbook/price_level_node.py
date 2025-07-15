from __future__ import annotations
from typing import Generic, TypeVar
from ..orders.order import Order

T = TypeVar("T", bound=Order)


class PriceLevelNode(Generic[T]):
    """
    Doubly linked list to house an order within
    a PriceLevel.
    """

    def __init__(
        self,
        order: T,
        prev: PriceLevelNode[T] | None = None,
        next: PriceLevelNode[T] | None = None,
    ):
        self.order = order
        self.prev = prev
        self.next = next
