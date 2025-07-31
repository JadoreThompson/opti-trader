from abc import abstractmethod
from asyncio import AbstractEventLoop, get_event_loop
from typing import Generic, TypeVar

from config import REDIS_CLIENT
from enums import ClientEventType, EventType, Side, InstrumentEventType
from models import RecentTrade
from services.payload_pusher import PusherPayload, PusherPayloadTopic
from ..enums import MatchOutcome
from ..orderbook import OrderBook
from ..orders import Order
from ..typing import (
    CloseRequestQuantity,
    MatchResult,
    CloseRequest,
    ModifyRequest,
    Queue,
    SupportsAppend,
)

O = TypeVar("O", bound=Order)


class BaseEngine(Generic[O]):
    def __init__(
        self,
        loop: AbstractEventLoop | None = None,
        queue: SupportsAppend | None = None,
    ) -> None:
        self._loop = loop or get_event_loop()
        self._queue = queue or Queue()

    @abstractmethod
    async def run(self) -> None:
        """
        Listens to the pubsub channel, routing each message
        to their respective native function.
        """

    @abstractmethod
    def place_order(self, payload: dict) -> None:
        """
        Places a new order based on the provided payload dictionary.

        This method handles the creation and insertion of orders into the
        appropriate order book. The payload should contain necessary order
        details like instrument, side, quantity, order type, and price.

        Args:
            payload (dict): A dictionary containing order parameters.
        """

    @abstractmethod
    def cancel_order(self, request: CloseRequest) -> None:
        """
        Cancels an existing order partially or fully.

        This method updates the position and order book to reflect the cancellation
        of a specified quantity of an open order.

        Args:
            request (CloseRequest): Data specifying the order ID and quantity to cancel.
        """

    @abstractmethod
    def modify_order(self, request: ModifyRequest) -> None:
        """
        Modifies parameters of an existing order.

        Allows updates such as changing the limit price, take profit, or stop loss
        for an open order. Handles updating the order book and position accordingly.

        Args:
            request (ModifyRequest): Data containing modifications to apply.
        """

    def _match(self, order: O, ob: OrderBook[O]) -> MatchResult:
        """
        Attempts to match the given order against the opposing side
        of the order book at the best available price.

        This method checks if the incoming order can be matched with
        existing resting orders at the top of the book (best bid or ask).

        Args:
            order (Order): The incoming order to be matched.
            ob (OrderBook): The order book containing resting orders.

        Returns:
            MatchResult: A tuple indicating whether the match succeeded, partially filled, or failed,
                        along with the match price and quantity filled.

        Match Outcomes:
            - SUCCESS: Full quantity matched at best price.
            - PARTIAL: Some quantity matched; remainder remains unfilled.
            - FAILURE: No matching possible (e.g., empty opposing book or price mismatch).
        """

        book_to_match = "asks" if order.side == Side.BID else "bids"
        starting_quantity = order.quantity - order.filled_quantity
        cur_quantity = starting_quantity

        target_price = ob.best_ask if order.side == Side.BID else ob.best_bid
        if target_price is None:
            return MatchResult(MatchOutcome.FAILURE, None, 0)

        for resting_order in ob.get_orders(target_price, book_to_match):
            if cur_quantity == 0:
                break

            if resting_order == order:
                continue

            resting_quantity = resting_order.quantity - resting_order.filled_quantity
            match_quantity = min(resting_quantity, cur_quantity)

            resting_order.filled_quantity += match_quantity
            cur_quantity -= match_quantity

            if resting_order.filled_quantity == resting_order.quantity:
                self._handle_filled_order(
                    resting_order, match_quantity, target_price, ob
                )
            else:
                self._handle_touched_order(
                    resting_order, match_quantity, target_price, ob
                )

        if cur_quantity == 0:
            return MatchResult(MatchOutcome.SUCCESS, target_price, starting_quantity)
        if cur_quantity == starting_quantity:
            return MatchResult(MatchOutcome.FAILURE, None, 0)
        return MatchResult(
            MatchOutcome.PARTIAL, target_price, starting_quantity - cur_quantity
        )

    @abstractmethod
    def _handle_filled_order(
        self,
        order: O,
        filled_quantity: int,
        price: float,
        ob: OrderBook[O],
    ) -> None: ...

    @abstractmethod
    def _handle_touched_order(
        self,
        order: O,
        filled_quantity: int,
        price: float,
        ob: OrderBook[O],
    ) -> None: ...

    @staticmethod
    def _validate_close_req_quantity(
        request_quantity: CloseRequestQuantity, base_quantity: int
    ) -> int:
        """
        Validates and resolves the close request quantity.

        Converts symbolic or explicit quantities to valid integers and
        raises an error if the input is invalid.

        Args:
            request_quantity (CloseRequestQuantity): Requested close amount
                ("ALL" or int).
            base_quantity (int): The maximum allowed quantity (open or standing).

        Returns:
            int: Validated quantity to close.

        Raises:
            ValueError: If the quantity is invalid or exceeds available quantity.
        """
        if request_quantity == "ALL":
            return base_quantity

        try:
            quantity = int(request_quantity)

            if quantity <= base_quantity:
                return quantity
        except TypeError:
            pass

        raise ValueError(f"Invalid request quantity {request_quantity}")

    def _update_price(self, instrument: str, price: float) -> None:
        if self._loop and self._loop.is_running():
            self._loop.create_task(self._send_price_update(instrument, price))

    def _push_order_payload(self, value: dict) -> None:
        payload = PusherPayload(
            action=PusherPayloadTopic.UPDATE, table_cls="Orders", data=value
        ).model_dump()
        self._queue.append(payload)

