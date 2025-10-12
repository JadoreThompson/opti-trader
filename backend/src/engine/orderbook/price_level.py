from .price_level_node import PriceLevelNode
from ..orders import Order


class PriceLevel:
    """
    Houses doubly linked list to manage orders at a single
    price level in an order book.

    Maintains insertion order for matching priority (FIFO)
    and provides efficient append and removal operations.

    Each order is wrapped in a PriceLevelNode and tracked via
    a lookup dictionary for O(1) access.
    """

    def __init__(self) -> None:
        self._head: PriceLevelNode | None = None
        self._tail: PriceLevelNode | None = None
        self._tracker: dict[str, PriceLevelNode] = {}

    def append(self, order: Order) -> None:
        """Adds a new order to the end of the level. Raises ValueError if duplicate."""
        if order.id in self._tracker:
            raise ValueError(f"Order with id {order.id} already on level.")

        new_node = PriceLevelNode(order)

        if self._head is None:
            self._head = new_node
            self._tail = new_node
        else:
            self._tail.next = new_node
            new_node.prev = self._tail
            self._tail = new_node

        self._tracker[order.id] = new_node

    def remove(self, order: Order) -> None:
        """Removes the specified order from the level. Safe against head/tail removals."""
        orders_node = self._tracker[order.id]

        if orders_node.prev is not None:
            orders_node.prev.next = orders_node.next

        if orders_node.next is not None:
            orders_node.next.prev = orders_node.prev

        if self._head == orders_node:
            self._head = orders_node.next

        if self._tail == orders_node:
            self._tail = orders_node.prev

        self._tracker.pop(order.id)

    def __bool__(self) -> bool:
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
