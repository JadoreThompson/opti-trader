from sortedcontainers.sorteddict import SortedDict
from typing import Iterable, KeysView, Literal

from engine.orderbook.price_level_node import PriceLevelNode
from enums import Side
from .price_level import PriceLevel
from ..order import Order

Book = Literal["bids", "asks"]


class OrderBook:
    """
    Manages the order book for a given trading instrument and
    maintains bid and ask price levels using sorted dictionaries.

    Attributes:
        _cur_price (float): The current market price of the instrument.
        _starting_price (float): The initial price when the book was created.
        _best_bid_price (float | None): Highest bid price available.
        _best_ask_price (float | None): Lowest ask price available.
        _bids (dict[float, PriceLevel]): Maps bid prices to price levels.
        _asks (dict[float, PriceLevel]): Maps ask prices to price levels.
        _bid_levels (dict_keys): View of all bid price levels.
        _ask_levels (dict_keys): View of all ask price levels.
    """

    def __init__(self, price=100.00) -> None:
        self._bids: dict[float, PriceLevel] = SortedDict()
        self._asks: dict[float, PriceLevel] = SortedDict()
        self._bid_levels = self._bids.keys()
        self._ask_levels = self._asks.keys()

        self._best_bid_price = None
        self._best_ask_price = None
        self._starting_price = price
        self._cur_price = round(price, 2)

    @property
    def price(self) -> float:
        return self._cur_price

    @property
    def bids(self) -> dict[float, PriceLevel]:
        return self._bids

    @property
    def asks(self) -> dict[float, PriceLevel]:
        return self._asks

    @property
    def bid_levels(self) -> KeysView[float]:
        return self._bid_levels

    @property
    def ask_levels(self) -> KeysView[float]:
        return self._ask_levels

    @property
    def best_bid(self) -> float | None:
        return self._best_bid_price

    @property
    def best_ask(self) -> float | None:
        return self._best_ask_price

    def append(self, order: Order, price: float) -> None:
        """
        Adds an order to the order book at the specified price level.

        Updates the best bid or ask price accordingly.

        Args:
            order (Order): The order to be added.
            price (float): Price level at which to place the order.

        Raises:
            ValueError: If the order side is invalid.
        """
        print("Appending with price:", price)
        if price < 0:
            raise RuntimeError()
        price = round(price, 2)

        if order.side == Side.BID:
            book = self._bids
            if self._best_bid_price is None or price > self._best_bid_price:
                self._best_bid_price = price
        elif order.side == Side.ASK:
            book = self._asks
            if self._best_ask_price is None or price < self._best_ask_price:
                self._best_ask_price = price
        else:
            raise ValueError(f"Invalid order side: {order.side}")

        book.setdefault(price, PriceLevel()).append(order)

    def remove(self, order: Order, price: float) -> None:
        """
        Removes an order from its associated price level.

        If the price level becomes empty after removal, it is deleted from the book,
        and the best bid/ask price is updated.

        Args:
            order (Order): The order to remove.
            price (float): The price level from which to remove the order.
        """
        if order.side == Side.BID:
            book = self._bids
        elif order.side == Side.ASK:
            book = self._asks
        else:
            return

        level = book[price]
        level.remove(order)

        if not level:
            if order.side == Side.BID:
                # print("Bid) Price:", self._best_bid_price, "PeekItem:", self._bids.peekitem(-1)[0])
                if price == self._bids.peekitem(-1)[0]:
                    self._best_bid_price = (
                        self._bids.peekitem(-2)[0] if len(self._bids) >= 2 else None
                    )
            else:
                # print("Asks) Price:", self._best_bid_price, "PeekItem:", self._asks.peekitem(0)[0])
                if price == self._asks.peekitem(0)[0]:
                    self._best_ask_price = (
                        self._asks.peekitem(1)[0] if len(self._asks) >= 2 else None
                    )

            book.pop(price)

    def set_price(self, price: float) -> None:
        self._cur_price = round(price, 2)

    def get_orders(self, price: float, book: Book) -> Iterable[Order] | None:
        """
        Retrieves all orders at a specific price level in the specified book.

        Args:
            price (float): The price level to query.
            book (str): Either 'bids' or 'asks'.

        Returns:
            Iterable[Order] | None: An iterable of orders at the price level, or an empty iterator
                if none exist.

        Raises:
            ValueError: If `book` is not 'bids' or 'asks'.
        """
        if book not in ("bids", "asks"):
            raise ValueError(f"Invalid book type: {book}. Must be 'bids' or 'asks'.")

        b = self._bids if book == "bids" else self._asks

        if price not in b:
            return iter([])

        level = b[price]
        cur = level.head

        while cur:
            yield cur.order
            cur = cur.next
