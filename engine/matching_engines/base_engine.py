import asyncio
import warnings

from typing import Iterable, TypedDict, List, overload
from r_mutex import LockClient

from enums import OrderStatus, Side
from ..enums import Tag
from ..order import Order
from ..orderbook.orderbook import OrderBook
from ..position import Position
from ..pusher import Pusher
from ..typing import MatchResult


class CancelOrderPayload(TypedDict):
    order_id: str
    instrument: str


class BaseEngine:
    def __init__(
        self,
        instrument_lock: LockClient,
        pusher: Pusher,
    ) -> None:
        self.instrument_lock = instrument_lock
        self.pusher = pusher
        self._order_books: dict[str, OrderBook] = {}

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
    ) -> MatchResult: ...

    @overload
    def place_order(self, payload: dict) -> None: ...

    def _handle_modify(self, payload: dict) -> None:
        """
        DONT USE !!!
        Handles the reassignment of values to an order within the orderbook

        Args:
            payload (dict)
        """
        pos = self._order_books[payload["instrument"]].get(payload["order_id"])
        if pos is None:
            return

        ob = self._order_books[pos.entry_order.payload["instrument"]]

        if pos.entry_order.payload["status"] == OrderStatus.PENDING:
            if payload["limit_price"] is not None:
                self._modify_limit_order(ob, pos, payload["limit_price"])

        if pos.entry_order.payload["status"] not in (
            OrderStatus.PENDING,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.CLOSED,
        ):
            self._modify_tp_sl(ob, pos, payload["take_profit"], payload["stop_loss"])

        self.pusher.append(pos.entry_order.payload)

    def _handle_cancel(self, payload: CancelOrderPayload) -> None:
        """
        DONT USE !!!

        Removes the order from tracking and the book and submits a
        balance update, giving the user the position amount
        Args:
            payload (CancelOrderPayload): _description_
        """
        ob = self._order_books[payload["instrument"]]
        pos = ob.get(payload["order_id"])

        if (
            pos.entry_order.payload["status"] != OrderStatus.PENDING
            or pos.entry_order.payload["standing_quantity"]
            != pos.entry_order.payload["quantity"]
        ):
            return

        ob.remove_all(pos.entry_order)
        self.pusher.append(
            {
                "user_id": pos.entry_order.payload["user_id"],
                "amount": pos.entry_order.payload["amount"],
            }
        )
        pos.entry_order.payload["status"] = OrderStatus.CLOSED
        self.pusher.append(pos.entry_order.payload, speed="fast")

    @overload
    def close_order(self, payload: dict) -> None: ...

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

    def _modify_limit_order(
        self,
        ob: OrderBook,
        pos: Position,
        new_limit_price: float,
    ) -> None:
        """DONT USE !!!"""
        pos.entry_order.payload["limit_price"] = new_limit_price
        ob.remove(pos.entry_order)
        ob.append(pos.entry_order, new_limit_price)

    def _modify_tp_sl(
        self,
        ob: OrderBook,
        pos: Position,
        new_take_profit: float = None,
        new_stop_loss: float = None,
    ) -> None:
        """
        DONT USE !!!
        Replacing of the position's entry, take profit and stop loss
        orders within the book to reflect the requested changes

        Args:
            ob (OrderBook)
            pos (Position)
            new_take_profit (float, optional) Defaults to None.
            new_stop_loss (float, optional) Defaults to None.
        """
        if new_take_profit is not None:
            pos.entry_order.payload["take_profit"] = new_take_profit

            if pos.take_profit_order is not None:
                ob.remove(pos.take_profit_order)

            if pos.take_profit_order is None:
                pos.take_profit_order = Order(
                    pos.entry_order.payload,
                    Tag.TAKE_PROFIT,
                    (
                        Side.BID
                        if pos.entry_order.payload["side"] == Side.ASK
                        else Side.BID
                    ),
                )

            ob.append(pos.take_profit_order, new_take_profit)

        if new_stop_loss is not None:
            pos.entry_order.payload["stop_loss"] = new_stop_loss

            if pos.stop_loss_order is not None:
                ob.remove(pos.stop_loss_order)

            if pos.stop_loss_order is None:
                pos.stop_loss_order = Order(
                    pos.entry_order.payload,
                    Tag.STOP_LOSS,
                    (
                        Side.BID
                        if pos.entry_order.payload["side"] == Side.ASK
                        else Side.BID
                    ),
                )

            ob.append(pos.stop_loss_order, new_stop_loss)
