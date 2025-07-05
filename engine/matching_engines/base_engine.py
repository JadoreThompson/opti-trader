import asyncio
from multiprocessing import Value
import warnings

from typing import Iterable, TypedDict, List, overload
from r_mutex import LockClient
from websockets import Close

from enums import OrderStatus, OrderType, Side
from ..enums import Tag
from ..order import Order
from ..orderbook.orderbook import OrderBook
from ..position import Position
from ..position_manager import PositionManager
from ..pusher import Pusher
from ..typing import MatchResult, ClosePayload, ModifyPayload


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
        self._position_manager = PositionManager()

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
    def place_order(self, payload: dict) -> None: ...

    @overload
    def close_order(self, payload: ClosePayload) -> None: ...

    def modify_position(self, data: ModifyPayload) -> None:
        """
        Handles the shuffling and value assignment of an existing
        position

        Args:
            data (ModifyPayload): Dictionary containing modification details.
        """
        pos = self._position_manager.get(data["order_id"])
        ob = self._order_books[pos.instrument]
        order = pos.entry_order
        payload = order.payload
        status = payload["status"]

        # Handle limit price field
        if data["limit_price"] is not None:
            if (
                status == OrderStatus.PENDING
                and payload["order_type"] == OrderType.LIMIT
            ):
                ob.remove(order, payload["limit_price"])
                ob.append(order, data["limit_price"])
                payload["limit_price"] = data["limit_price"]
            else:
                raise ValueError(
                    f"Cannot change limit price for order with order status {OrderStatus.PENDING} and order type {OrderType.LIMIT}"
                )

        # Handle TP SL price
        payload["take_profit"] = data["take_profit"]
        payload["stop_loss"] = data["stop_loss"]

        if status not in (OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED):
            if data["take_profit"] != payload["take_profit"] and pos.take_profit_order:
                ob.remove(pos.take_profit_order)
            if data["stop_loss"] != payload["stop_loss"] and pos.stop_loss_order:
                ob.remove(pos.stop_loss_order)

            self._place_tp_sl(order, ob)

        self.pusher.append(payload)

    @overload
    def _match(
        self,
        order: dict,
        order_side: Side,
        ob: OrderBook,
        price: float,
    ) -> MatchResult: ...

    def _handle_cancel(self, payload: ClosePayload) -> None:
        """
        DONT USE !!!

        Removes the order from tracking and the book and submits a
        balance update, giving the user the position amount
        Args:
            payload (CancelOrderPayload): _description_
        """
        pos = self._position_manager.get(payload['order_id'])
        order = pos.entry_order
        
        if order.payload['status'] != OrderStatus.PENDING:
            raise ValueError("Cannot cancel order with status {order.payload['status']}. Must have status '{OrderStatus.PENDING}'.")
        
        ob = self._order_books[pos.instrument]

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
