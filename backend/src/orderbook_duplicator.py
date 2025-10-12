from sortedcontainers import SortedDict

from engine.models import Event
from enums import EventType, Side


class OrderEntry:
    def __init__(
        self, executed_quantity: float, quantity: float, price: float, side: Side
    ):
        self.executed_quantity = executed_quantity
        self.quantity = quantity
        self.price = price
        self.side = side


class OrderBookReplicator:
    """
    Maintains a replicated orderbook for an instrument,
    by consuming order/trade events from the matching engine.
    This book is used for publishing snapshots to clients/frontends.
    """

    def __init__(self, size: int = 10):
        # { price: quantity }
        self._bids: SortedDict[float, float] = SortedDict()
        self._asks: SortedDict[float, float] = SortedDict()
        self._orders: dict[str, OrderEntry] = {}
        self.size = size

        self._handlers = {
            EventType.ORDER_PLACED: self._handle_order_placed,
            EventType.ORDER_PARTIALLY_FILLED: self._handle_order_filled,
            EventType.ORDER_FILLED: self._handle_order_filled,
            EventType.ORDER_CANCELLED: self._handle_order_cancelled,
            EventType.ORDER_MODIFIED: self._handle_order_modified,
        }

    def process_event(self, event: Event) -> None:
        handler = self._handlers.get(event.event_type)
        if handler:
            handler(event)

    def _get_book(self, side: Side) -> SortedDict:
        return self._bids if side == Side.BID else self._asks

    def _update_level(self, book: SortedDict, price: float, delta: float) -> None:
        """
        Add or remove quantity from a price level.
        If the resulting quantity is 0, the level is deleted.
        """
        if delta == 0:
            return

        new_qty = book.get(price, 0.0) + delta
        if new_qty == 0:
            book.pop(price, None)
        else:
            book[price] = new_qty

    def _handle_order_placed(self, event: Event):
        details = event.details
        order = OrderEntry(
            executed_quantity=details["executed_quantity"],
            quantity=details["quantity"],
            price=details["price"],
            side=details["side"],
        )
        self._orders[event.related_id] = order

        remaining = order.quantity - order.executed_quantity
        self._update_level(self._get_book(order.side), order.price, remaining)

    def _handle_order_filled(self, event: Event):
        details = event.details
        order = self._orders.get(event.related_id)
        if not order:
            return

        prev_remaining = order.quantity - order.executed_quantity
        new_remaining = details["quantity"] - details["executed_quantity"]

        delta = new_remaining - prev_remaining
        self._update_level(self._get_book(order.side), order.price, delta)

        order.quantity = details["quantity"]
        order.executed_quantity = details["executed_quantity"]

        if order.quantity == order.executed_quantity:
            self._orders.pop(event.related_id)

    def _handle_order_cancelled(self, event: Event):
        order = self._orders.pop(event.related_id, None)
        if order:
            remaining = order.quantity - order.executed_quantity
            self._update_level(self._get_book(order.side), order.price, -remaining)

    def _handle_order_modified(self, event: Event):
        details = event.details
        order = self._orders.get(event.related_id)
        if not order:
            return

        book = self._get_book(order.side)
        old_remaining = order.quantity - order.executed_quantity

        self._update_level(book, order.price, -old_remaining)

        order.price = details["price"]
        order.quantity = details.get("quantity", order.quantity)
        order.executed_quantity = details.get(
            "executed_quantity", order.executed_quantity
        )

        new_remaining = order.quantity - order.executed_quantity
        self._update_level(book, order.price, new_remaining)

    def snapshot(self) -> dict[str, dict[float, float]]:
        """
        Return a snapshot of top N bids and asks.
        """
        bids: dict[float, float] = {}
        bid_depth = min(self.size, len(self._bids))
        for i in range(-1, -bid_depth - 1, -1):
            price, qty = self._bids.peekitem(i)
            bids[price] = qty

        asks: dict[float, float] = {}
        ask_depth = min(self.size, len(self._asks))
        for i in range(ask_depth):
            price, qty = self._asks.peekitem(i)
            asks[price] = qty

        return {"bids": bids, "asks": asks}
