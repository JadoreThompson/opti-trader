import asyncio
import warnings

from typing import Iterable, List, overload
from r_mutex import Lock

from enums import Side
from .order import Order
from .orderbook import OrderBook
from .pusher import Pusher
from .utils import MatchResult


class BaseEngine:
    def __init__(
        self,
        instrument_lock: Lock,
        pusher: Pusher,
    ) -> None:
        self.instrument_lock = instrument_lock
        self.pusher = pusher
        self._order_books: dict[str, OrderBook] = None

    async def run(self, instruments: List[str] = None):
        """
        Initializes the engine and starts the pusher.

        This method sets up the connection to the pusher and waits for it to start.
        Args:
            instruments (list[str]): A list of instruments of which OrderBook objects
                will be initialised for. Defaults to ["BTCUSD"]
        Raises:
            RuntimeError: Pusher failed to connect within 210 seconds
        """
        asyncio.create_task(self.pusher.run())

        i = 0
        while i < 20:
            if self.pusher.is_running:
                break
            i += 1
            m = f"Waiting for pusher - Sleeping for {i} seconds"
            warnings.warn(m)
            await asyncio.sleep(i)

        if i == 20:
            raise RuntimeError("Failed to connect to pusher")

        if instruments is None:
            instruments = ["BTCUSD"]

        self._order_books = {
            instr: OrderBook(instr, self.instrument_lock, 37, self.pusher)
            for instr in instruments
        }

        await self._listen()

    @overload
    async def _listen(self) -> None: ...

    @overload
    def _match(
        self,
        order: dict,
        order_side: Side,
        ob: OrderBook,
        price: float,
        max_attempts: int = 5,
        attempt: int = 0,
    ) -> MatchResult: ...
    
    @overload
    def _handle_market_order(self, order: Order, ob: OrderBook) -> MatchResult: ...

    @overload
    def _handle_limit_order(self, order: Order, ob: OrderBook) -> None: ...

    @overload
    def _handle_new(self, payload: dict) -> None: ...
    
    @overload
    def _handle_modify(self, payload: dict) -> None: ...
    
    @overload
    def _handle_close(self, payload: dict) -> None: ...

    @overload
    def _place_tp_sl(self, order: Order, ob: OrderBook) -> None: ...

    @overload
    def _handle_filled_orders(
        self, orders: Iterable[tuple[Order, int]], ob: OrderBook, price: float
    ) -> None: ...

    @overload
    def _handle_touched_orders(
        self,
        orders: Iterable[Order],
        price: float,
        ob: OrderBook,
        filled_orders: list[tuple[Order, int]],
    ) -> None: ...

    @overload
    def _handle_modify_order(self, payload: dict): ...
