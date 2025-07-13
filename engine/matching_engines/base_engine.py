from typing import overload
from enums import OrderStatus, Side

from ..enums import MatchOutcome, Tag
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

    # @overload
    # def _handle_filled_order(
    #     self,
    #     order: Order,
    #     filled_quantity: int,
    #     price: float,
    #     ob: OrderBook,
    # ) -> None: ...

    # @overload
    # def _handle_touched_order(
    #     self,
    #     order: Order,
    #     filled_quantity: int,
    #     price: float,
    #     ob: OrderBook,
    # ) -> None: ...

    def _handle_filled_order(
        self,
        order: Order,
        filled_quantity: int,
        price: float,
        ob: OrderBook,
    ) -> None:
        """
        Applies fill effects to positions, removes orders from the book, and
        finalizes positions if closed.

        Args:
            order (Order): Touched order.
            touched_quantity (int): Touched quantity.
            price (float): Execution price.
            ob (OrderBook): Relevant order book.
        """
        pos = self._position_manager.get(order.id)

        if order.tag == Tag.ENTRY:
            pos.apply_entry_fill(filled_quantity, price)
            ob.remove(order, order.price)

            if pos.take_profit_order is not None or pos.stop_loss_order is not None:
                self._mutate_tp_sl_quantity(pos)
            else:
                self._place_tp_sl(pos, ob)
        else:
            pos.apply_close(filled_quantity, price)
            self._remove_tp_sl(pos, ob)

            if pos.status == OrderStatus.CLOSED:
                self._position_manager.remove(pos.id)

    def _handle_touched_order(
        self,
        order: Order,
        touched_quantity: int,
        price: float,
        ob: OrderBook,
    ) -> None:
        """
        Updates positions with touched quantities and adjusts TP/SL accordingly.

        Args:
            order (Order): Touched order.
            touched_quantity (int): Touched quantity.
            price (float): Execution price.
            ob (OrderBook): Relevant order book.
        """
        pos = self._position_manager.get(order.id)

        if order.tag == Tag.ENTRY:
            pos.apply_entry_fill(touched_quantity, price)

            if pos.take_profit_order is not None or pos.stop_loss_order is not None:
                self._mutate_tp_sl_quantity(pos)
            else:
                self._place_tp_sl(pos, ob)
        else:
            pos.apply_close(touched_quantity, price)
            self._mutate_tp_sl_quantity(pos)
