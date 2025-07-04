from sortedcontainers.sorteddict import SortedDict
from typing import Iterable, KeysView, Literal

from enums import Side
from .orderbook_item import OrderbookItem
from .node import Node
from ..enums import Tag
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

    def __init__(self, price=100.0) -> None:
        self._bids: dict[float, OrderbookItem] = SortedDict()
        self._asks: dict[float, OrderbookItem] = SortedDict()
        self._bid_levels = self._bids.keys()
        self._ask_levels = self._asks.keys()
        self._best_bid_price = None
        self._best_ask_price = None
        self._starting_price = price
        self._cur_price = price
        self._pos_tracker: dict[str, Position] = {}

    def append(self, order: Order, price: float | None = None) -> None:
        """
        Appends order to tracking and to the book

        Args:
            order (Order)
            price (float) - Price level to be appended to
        """
        # print(locals())
        if price is not None:
            price = round(price, 2)
        else:
            price = self._cur_price

        if order.side == Side.BID:
            ob_item = self._bids.setdefault(price, OrderbookItem())
        elif order.side == Side.ASK:
            ob_item = self._asks.setdefault(price, OrderbookItem())
        else:
            raise ValueError(f"Invalid order side: {order.side}")

        if order.payload["order_id"] in ob_item.tracker:
            raise ValueError(
                f"Order with id {order.payload['order_id']} already on level."
            )

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

    def remove(self, order: Order, price: float) -> None:
        """
        Removes an order from the price level it situates. To be used
        when an order isn't in the filled state since it won't be situated
        within a price level. However it's stop loss and take profit order object
        can utilise this since they'll be situated in a price level.

        Args:
            order (Order)
        """
        if order.side == Side.BID:
            ob_item = self._bids[price]
            book = self._bids
        elif order.side == Side.ASK:
            ob_item = self._asks[price]
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

        if ob_item.head is None and len(book) > 1:
            book.pop(price, None)

        # Invalidation
        if self._best_bid_price == price and self._bids.get(price) is None:
            self._best_bid_price = None

        if self._best_ask_price == price and self._asks.get(price) is None:
            self._best_ask_price = None

    def get(self, order_id: str) -> Position | None:
        """
        DO NOT CALL !!!
        Retrieves the position object belonging to the order_id
        Args:
            order_id (str)
        Returns:
            Position or None: Returns the position object if it exists, otherwise None.
        """
        return self._pos_tracker.get(order_id)

    def track(self, order: Order) -> Position:
        """
        DO NOT CALL !!!
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

        pos = self._pos_tracker[order.payload["order_id"]]

        if order.tag == Tag.STOP_LOSS:
            pos.stop_loss_order = order
        else:
            pos.take_profit_order = order

        return pos

    def set_price(self, price: float) -> None:
        price = round(price, 2)
        self._cur_price = price
        self._best_bid_price = self._find_best_bid(price)
        self._best_ask_price = self._find_best_ask(price)

    def _find_best_bid(self, price: float) -> float | None:
        """Find highest bid price <= current price that has orders"""
        idx = self._bids.bisect_right(price)

        for i in range(idx - 1, -1, -1):
            bid_price = self._bids.peekitem(i)[0]

            if self._bids[bid_price].head is not None:
                return round(bid_price, 2)

        return price

    def _find_best_ask(self, price: float) -> float | None:
        """Find lowest ask price >= current price that has orders"""
        idx = self._asks.bisect_right(price)

        for i in range(idx, len(self._asks)):
            ask_price = self._asks.peekitem(i)[0]

            if self._asks[ask_price].head is not None:
                return round(ask_price, 2)

        return price

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
        # print("lll", self.asks[self._best_ask_price])
        if self._best_ask_price is None:
            self._best_ask_price = self._find_best_ask(self._cur_price)
        elif self._best_ask_price not in self.ask_levels:
            self._best_ask_price = self._find_best_ask(self._best_ask_price)
        elif (
            len(self._ask_levels) > 1 and self._asks[self._best_ask_price].head == None
        ):
            self._asks.pop(self._best_ask_price)
            self._best_ask_price = self._find_best_ask(self._best_ask_price)
        return self._best_ask_price
