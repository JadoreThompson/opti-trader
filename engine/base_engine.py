import asyncio
import warnings

from typing import Iterable, TypedDict, List, overload
from r_mutex import Lock

from enums import OrderStatus, Side
from .enums import Tag
from .exceptions import PositionNotFound
from .order import Order
from .orderbook import OrderBook
from .position import Position
from .pusher import Pusher
from .utils import MatchResult


class CancelOrderPayload(TypedDict):
    order_id: str
    instrument: str


class BaseEngine:
    def __init__(
        self,
        instrument_lock: Lock,
        pusher: Pusher,
    ) -> None:
        self.instrument_lock = instrument_lock
        self.pusher = pusher
        self._order_books: dict[str, OrderBook] = None

    async def run(self, instruments: List[str]) -> None:
        """
        Initializes the engine and starts the pusher.

        This method sets up the connection to the pusher and waits for it to start.
        Args:
            instruments (list[str]): A list of instruments of which OrderBook objects
                will be initialised for.
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
    def _handle_new(self, payload: dict) -> None: ...

    @overload
    def _handle_modify(self, payload: dict) -> None: ...

    def _handle_cancel(self, payload: CancelOrderPayload) -> None:
        """
        Removes the order from tracking and the book and submits a
        balance update, giving the user the position amount
        Args:
            payload (CancelOrderPayload): _description_
        """
        try:
            ob = self._order_books[payload["instrument"]]
            pos = ob.get(payload["order_id"])
        except PositionNotFound:
            return

        if (
            pos.order.payload["status"] != OrderStatus.PENDING
            or pos.order.payload["standing_quantity"] != pos.order.payload["quantity"]
        ):
            return

        ob.remove_all(pos.order)
        self.pusher.append(
            {
                "user_id": pos.order.payload["user_id"],
                "amount": pos.order.payload["amount"],
            }
        )
        pos.order.payload["status"] = OrderStatus.CLOSED
        self.pusher.append(pos.order.payload, speed="fast")

    @overload
    def _handle_close(self, payload: dict) -> None: ...

    @overload
    def _handle_market_order(self, order: Order, ob: OrderBook) -> MatchResult: ...

    @overload
    def _handle_limit_order(self, order: Order, ob: OrderBook) -> None: ...

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

    def _handle_modify(self, payload: dict) -> None:
        """
        Handles the reassignment of values to an order within the orderbook

        Args:
            payload (dict)
        """
        try:
            pos = self._order_books[payload["instrument"]].get(payload["order_id"])
            ob = self._order_books[pos.order.payload["instrument"]]
        except PositionNotFound:
            return

        if pos.order.payload["status"] == OrderStatus.PENDING:
            if payload["limit_price"] is not None:
                self._modify_limit_order(ob, pos, payload["limit_price"])

        if pos.order.payload["status"] not in (
            OrderStatus.PENDING,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.CLOSED,
        ):
            self._modify_tp_sl(ob, pos, payload["take_profit"], payload["stop_loss"])

        self.pusher.append(pos.order.payload)

    def _modify_limit_order(
        self,
        ob: OrderBook,
        pos: Position,
        new_limit_price: float,
    ) -> None:
        pos.order.payload["limit_price"] = new_limit_price
        ob = self._order_books[pos.order.payload["instrument"]]
        ob.remove(pos.order)
        ob.append(pos.order, new_limit_price)

    def _modify_tp_sl(
        self,
        ob: OrderBook,
        pos: Position,
        new_take_profit: float = None,
        new_stop_loss: float = None,
    ) -> None:
        """
        Replacing of the position's entry, take profit and stop loss
        orders within the book to reflect the requested changes

        Args:
            ob (OrderBook)
            pos (Position)
            new_take_profit (float, optional) Defaults to None.
            new_stop_loss (float, optional) Defaults to None.
        """
        if new_take_profit is not None:
            pos.order.payload["take_profit"] = new_take_profit

            if pos.take_profit is not None:
                ob.remove(pos.take_profit)

            if pos.take_profit is None:
                pos.take_profit = Order(
                    pos.order.payload,
                    Tag.TAKE_PROFIT,
                    (Side.BUY if pos.order.payload["side"] == Side.SELL else Side.BUY),
                )

            ob.append(pos.take_profit, new_take_profit)

        if new_stop_loss is not None:
            pos.order.payload["stop_loss"] = new_stop_loss

            if pos.stop_loss is not None:
                ob.remove(pos.stop_loss)

            if pos.stop_loss is None:
                pos.stop_loss = Order(
                    pos.order.payload,
                    Tag.STOP_LOSS,
                    (Side.BUY if pos.order.payload["side"] == Side.SELL else Side.BUY),
                )

            ob.append(pos.stop_loss, new_stop_loss)
