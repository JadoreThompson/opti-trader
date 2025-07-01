from sortedcontainers.sorteddict import SortedDict
from typing import Iterable, KeysView, Literal

from .orderbook_item import OrderbookItem
from enums import Side
from ..enums import Tag
from ..exceptions import PositionNotFound
from .node import Node
from ..order import Order
from ..position import Position

Book = Literal["bids", "asks"]


class OrderBook:
    """
    Manages the order book for a given trading instrument, handling bid and ask orders,
    price updates, and order tracking.

    The OrderBook maintains separate dictionaries for bids and asks, allowing efficient
    order management. It also tracks positions and updates unrealized profit/loss (UPL)
    based on price changes.

    Attributes:
        _cur_price (float): The current market price of the instrument.
        _price_delay (float): The delay (in seconds) between price updates.
        _price_queue (deque): A queue storing price updates. Used to enable throttling of
            price upates
        pusher (Pusher): Used for consolidating updates to records of orders in DB
        bids (dict[float, list[Order]]): Stores bid orders, grouped by price level.
        asks (dict[float, list[Order]]): Stores ask orders, grouped by price level.
        bid_levels (dict_keys): A view of the bid price levels.
        ask_levels (dict_keys): A view of the ask price levels.
        _tracker (dict[str, Position]): Tracks positions associated with order IDs.
    """

    def __init__(self) -> None:
        self._bids: dict[float, OrderbookItem] = SortedDict()
        self._asks: dict[float, OrderbookItem] = SortedDict()
        self._bid_levels = self._bids.keys()
        self._ask_levels = self._asks.keys()
        self._best_bid_price = None
        self._best_ask_price = None
        self._cur_price = 0.0
        self._tracker: dict[str, Position] = {}

    def append(self, order: Order, price: float) -> Position:
        """
        Appends order to tracking and to the book

        Args:
            order (Order)
            price (float) - Price level to be appended to
        """
        pos: Position | None = self.get(order.payload["order_id"])

        if pos is not None:
            if order.tag == Tag.TAKE_PROFIT:
                pos.take_profit = order
            else:
                pos.stop_loss = order
        else:
            if order.tag != Tag.ENTRY:
                raise ValueError("Cannot append non-entry order without a position.")

            pos = Position(order)
            self._tracker[order.payload["order_id"]] = pos

        if order.side == Side.BUY:
            ob_item = self._bids.setdefault(price, OrderbookItem())
        elif order.side == Side.SELL:
            ob_item = self._asks.setdefault(price, OrderbookItem())
        else:
            raise ValueError(f"Invalid order side: {order.side}")

        new_node = Node(order)
        head = ob_item.head

        if head is None:
            ob_item.head = new_node
            ob_item.tail = new_node
        else:
            ob_item.tail.next = new_node
            new_node.prev = ob_item.tail
            ob_item.tail = new_node

        ob_item.tracker[order.payload["order_id"]] = new_node

        return pos

    def remove(self, order: Order) -> None:
        """
        Removes an order from the price level it situates. To be used
        when an order isn't in the filled state since it won't be situated
        within a price level. However it's stop loss and take profit order object
        can utilise this since they'll be situated in a price level.

        Args:
            order (Order)
        """
        if order.tag == Tag.ENTRY:
            price = order.payload["limit_price"] or order.payload["price"]
        elif order.tag == Tag.TAKE_PROFIT:
            price = order.payload["take_profit"]
        elif order.tag == Tag.STOP_LOSS:
            price = order.payload["stop_loss"]
        else:
            raise ValueError(f"Invalid order tag: {order.tag}")

        if order.side == Side.BUY:
            ob_item = self._bids.get(price)
            if ob_item is None:
                return

            orders_node = ob_item.tracker[order.payload["order_id"]]
            book = self._bids

        elif order.side == Side.SELL:
            ob_item = self._asks.get(price)
            if ob_item is None:
                return

            orders_node = ob_item.tracker[order.payload["order_id"]]
            book = self._asks

        # Remove the order from the tracker
        orders_node = ob_item.tracker[order.payload["order_id"]]

        if orders_node.prev is not None:
            orders_node.prev.next = orders_node.next

        if orders_node.next is not None:
            orders_node.next.prev = orders_node.prev

        if ob_item.head == orders_node:
            ob_item.head = orders_node.next

        if ob_item.tail == orders_node:
            ob_item.tail = orders_node.prev

        # Cleanup
        orders_node.prev = None
        orders_node.next = None
        ob_item.tracker.pop(order.payload["order_id"], None)

        if ob_item.head is None:
            book.pop(price, None)

        # Invalidation
        if self._best_bid_price == price:
            self._best_bid_price = None
        if self._best_ask_price == price:
            self._best_ask_price = None

    def remove_all(self, order: Order) -> Position | None:
        """
        Removes the order and it's counterparts both from the
        tracker and their corresponding price levels

        Args:
            order (Order)
        Returns:
            Position or None: Returns the position object if it exists, otherwise None.
        """
        pos: Position | None = self._tracker.pop(order.payload["order_id"], None)
        if pos is None:
            return

        self.remove(order)

        if pos.take_profit is not None:
            self.remove(pos.take_profit)
        if pos.stop_loss is not None:
            self.remove(pos.stop_loss)
        return pos

    def get(self, order_id: str) -> Position | None:
        """
        Retrieves the position object belonging to the order_id

        Args:
            order_id (str)
        Returns:
            Position or None: Returns the position object if it exists, otherwise None.
        """
        return self._tracker.get(order_id)

    def track(self, order: Order) -> Position:
        """
        Appends an order to the tracker. If this is a take profit or stop loss
        order, it's appended to the position.

        Args:
            order (Order)

        Returns:
            Position
        """
        if order.tag == Tag.ENTRY:
            raise ValueError(
                "Cannot track an entry order directly. Use append instead."
            )

        pos = self._tracker.get(order.payload["order_id"])

        if not pos:
            raise PositionNotFound("Position not found for the given order ID.")

        if order.tag == Tag.STOP_LOSS:
            pos.stop_loss = order
        else:
            pos.take_profit = order

        return pos

    def set_price(self, price: float) -> None:
        self._best_bid_price = self._find_best_bid(price)
        self._best_ask_price = self._find_best_ask(price)

    def _find_best_bid(self, price: float) -> float | None:
        """Find highest bid price <= current price that has orders"""
        idx = self._bids.bisect_right(price)

        for i in range(idx - 1, -1, -1):
            bid_price = self._bids.peekitem(i)[0]

            if self._bids[bid_price].head is not None:
                return bid_price

        return None

    def _find_best_ask(self, price: float) -> float | None:
        """Find lowest ask price >= current price that has orders"""
        idx = self._asks.bisect_left(price)

        for i in range(idx, len(self._asks)):
            ask_price = self._asks.peekitem(i)[0]

            if self._asks[ask_price].head is not None:
                return ask_price

        return None

    def get_orders(self, price: float, book: Book) -> Iterable[Order] | None:
        if book not in ("bids", "asks"):
            raise ValueError(f"Invalid book type: {book}. Must be 'bids' or 'asks'.")

        b = self._bids if book == "bids" else self._asks

        if price not in b:
            return iter([])

        ob_item = b[price]
        cur = ob_item.head

        while cur:
            yield cur.order
            cur = cur.next

    def get_bids(self, price: float) -> Iterable[Order] | None:
        if price not in self._bids:
            return

        ob_item = self._bids[price]
        cur = ob_item.head

        while ob_item.head:
            yield cur.order
            ob_item.head = cur.next
            cur = cur.next

    @property
    def bids(self) -> dict[float, OrderbookItem]:
        return self._bids

    @property
    def asks(self) -> dict[float, OrderbookItem]:
        return self._asks

    @property
    def bid_levels(self) -> KeysView[float]:
        return self._bid_levels

    @property
    def ask_levels(self) -> KeysView[float]:
        return self._ask_levels

    @property
    def best_bid(self) -> float | None:
        if self._best_bid_price is None:
            self._best_bid_price = self._find_best_bid(self._cur_price)
        return self._best_bid_price

    @property
    def best_ask(self) -> float | None:
        if self._best_ask_price is None:
            self._best_ask_price = self._find_best_ask(self._cur_price)
        return self._best_ask_price

    # def __getitem__(self, book: Book) -> dict:
    #     if book not in ("bids", "asks"):
    #         raise ValueError(f"Invalid book type: {book}. Must be 'bids' or 'asks'.")
    #     return self._bids if book == "bids" else self.asks

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"Orderbook({self.instrument}, price={self.price}, bids={sum(len(self._bids[key]) for key in self._bids)}, asks={sum(len(self.asks[key]) for key in self.asks)})"
