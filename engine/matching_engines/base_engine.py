from typing import Generic, Type, overload, TypeVar

from enums import Side
from ..enums import MatchOutcome
from ..orders.order import Order
from ..orderbook.orderbook import OrderBook
from ..positions.base_position import BasePosition
from ..position_manager import PositionManager
from ..typing import MatchResult, CloseRequest, ModifyRequest

T = TypeVar("T", bound=BasePosition)


class BaseEngine(Generic[T]):
    def __init__(self, position_cls: Type[T]) -> None:
        self._orderbooks: dict[str, OrderBook] = {}
        self._position_manager = PositionManager(position_cls)

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
        
    def _mutate_tp_sl_quantity(self, pos: T) -> None:
        """
        Adjusts TP/SL order quantities to match current open position quantity.

        Args:
            pos (Position): Position whose TP/SL orders should be updated.
        """
        if pos.take_profit_order is not None:
            pos.take_profit_order.quantity = pos.open_quantity
            pos.take_profit_order.filled_quantity = 0
        if pos.stop_loss_order is not None:
            pos.stop_loss_order.quantity = pos.open_quantity
            pos.stop_loss_order.filled_quantity = 0
    
    def _remove_tp_sl(self, pos: T, ob: OrderBook) -> None:
        """
        Removes take-profit and stop-loss orders associated with a position.

        Args:
            pos (Position): The position whose TP/SL orders should be removed.
            ob (OrderBook): Order book from which to remove the orders.
        """
        if pos.take_profit_order is not None:
            ob.remove(pos.take_profit_order, pos.take_profit_order.price)
            pos.take_profit_order = None
        if pos.stop_loss_order is not None:
            ob.remove(pos.stop_loss_order, pos.stop_loss_order.price)
            pos.stop_loss_order = None

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
