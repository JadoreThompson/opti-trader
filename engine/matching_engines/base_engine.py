from typing import overload
from enums import Side

from ..enums import MatchOutcome
from ..order import Order
from ..orderbook.orderbook import OrderBook
from ..position_manager import PositionManager
from ..typing import MatchResult, CloseRequest, ModifyRequest


class BaseEngine:
    def __init__(
        self,
    ) -> None:
        self._orderbooks: dict[str, OrderBook] = {}
        self._position_manager = PositionManager()

    @overload
    def place_order(self, payload: dict) -> None:
        """
        Places a new order based on the provided payload dictionary.

        This method handles the creation and insertion of orders into the
        appropriate order book. The payload should contain necessary order
        details like instrument, side, quantity, order type, and price.

        Args:
            payload (dict): A dictionary containing order parameters.
        """

    @overload
    def cancel_order(self, request: CloseRequest) -> None:
        """
        Cancels an existing order partially or fully.

        This method updates the position and order book to reflect the cancellation
        of a specified quantity of an open order.

        Args:
            request (CloseRequest): Data specifying the order ID and quantity to cancel.
        """

    @overload
    def close_order(self, request: CloseRequest) -> None:
        """
        Closes (partially or fully) an open position.

        Processes a close request by matching it against the opposing side of the
        order book, updating position status, and cleaning up related orders.

        Args:
            request (CloseRequest): Data specifying the order ID and quantity to close.
        """

    @overload
    def modify_order(self, request: ModifyRequest) -> None:
        """
        Modifies parameters of an existing order.

        Allows updates such as changing the limit price, take profit, or stop loss
        for an open order. Handles updating the order book and position accordingly.

        Args:
            request (ModifyRequest): Data containing modifications to apply.
        """

    def _match(self, order: Order, ob: OrderBook) -> MatchResult:
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
            if resting_quantity < 0:
                raise RuntimeError()

            match_quantity = min(resting_quantity, cur_quantity)
            if match_quantity < 0:
                raise RuntimeError()

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

    @overload
    def _handle_filled_order(
        self,
        order: Order,
        filled_quantity: int,
        price: float,
        ob: OrderBook,
    ) -> None: ...

    @overload
    def _handle_touched_order(
        self,
        order: Order,
        filled_quantity: int,
        price: float,
        ob: OrderBook,
    ) -> None: ...
