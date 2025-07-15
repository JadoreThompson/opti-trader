from datetime import datetime
from enums import OrderStatus, Side
from .orders import Order


class Position:
    """
    Manages the complete lifecycle and state of a trading position,
    from pending to closed or cancelled.

    This class is the single source of truth for its state. The engine
    tells it *what* happened (e.g., 'a fill occurred'), and this class
    updates its internal state accordingly.
    """

    def __init__(
        self,
        payload: dict,
        entry_order: Order | None = None,
        take_profit_order: Order | None = None,
        stop_loss_order: Order | None = None,
    ):
        self._payload = payload
        self.entry_order = entry_order
        self.stop_loss_order = stop_loss_order
        self.take_profit_order = take_profit_order
        self._filled_price = 0.0
        self._filled_quantity = 0

    @property
    def id(self) -> int:
        return self._payload["order_id"]

    @property
    def instrument(self) -> str:
        return self._payload["instrument"]

    @property
    def status(self):
        return self._payload["status"]

    @property
    def payload(self) -> dict:
        """Returns the current state payload."""
        return self._payload

    @property
    def open_quantity(self) -> int:
        return self._payload["open_quantity"]

    @property
    def standing_quantity(self) -> int:
        return self._payload["standing_quantity"]

    def apply_entry_fill(self, quantity: int, price: float) -> None:
        """
        Applies a fill to the entry order of the position.

        This method updates the position's internal state to reflect a filled quantity at the given price.
        It reduces the standing quantity, increases the open quantity, tracks the filled price,
        recalculates the filled price and unrealised PnL.

        Args:
            quantity (int): The quantity filled in this execution.
            price (float): The execution price of the fill.


        Side Effects:
            - Updates standing and open quantities in the payload.
            - Updates the internal record of filled prices.
            - Recomputes the filled price.
            - Updates unrealised PnL.
            - Adjusts the order status PARTIALLY_FILLED or FILLED.
            - Clears the entry order if fully filled.
        """
        if quantity <= 0:
            return

        self._payload["standing_quantity"] -= quantity
        self._payload["open_quantity"] += quantity

        self._filled_price += price * quantity
        self._filled_quantity += quantity
        self._payload["filled_price"] = self._calculate_filled_price()
        self.update_upnl(price)

        if self.standing_quantity > 0:
            self._payload["status"] = OrderStatus.PARTIALLY_FILLED
        else:
            self._payload["status"] = OrderStatus.FILLED
            self.entry_order = None  # The entry order is now fully filled

    def apply_close(self, quantity: int, price: float) -> None:
        """
        Applies a closing fill to the position (e.g., from TP, SL, or manual action).

        Updates the realised PnL, reduces the open quantity, and adjusts the position status accordingly.

        Args:
            quantity (int): The quantity closed in this execution.
            price (float): The execution price of the close.

        Side Effects:
            - Recalculates realised PnL.
            - Decreases open quantity.
            - Recalculates unrealised PnL.
            - Updates position status to PARTIALLY_CLOSED or CLOSED.
            - Sets close time and close price if position is fully closed.
        """

        if quantity <= 0:
            return

        self._payload["realised_pnl"] += self._calculate_pnl(price, quantity)
        self._payload["open_quantity"] -= quantity
        self.update_upnl(price)

        if self.status == OrderStatus.PARTIALLY_FILLED:
            return

        if self.open_quantity == 0:
            self._payload["status"] = OrderStatus.CLOSED
            self._payload["closed_at"] = datetime.now()
            self._payload["closed_price"] = price
        else:
            self._payload["status"] = OrderStatus.PARTIALLY_CLOSED

    def apply_cancel(self, quantity: int) -> None:
        """
        Applies a cancellation to the standing quantity of the order.

        Decreases the standing quantity and updates the order status based on the result.
        Handles transitions to CANCELLED or FILLED, and sets the close timestamp if fully cancelled.

        Args:
            quantity (int): The quantity to cancel.

        Side Effects:
            - Reduces the standing quantity.
            - If fully cancelled from PENDING state, sets status to CANCELLED and timestamps closure.
            - If remaining quantity is 0 from PARTIALLY_FILLED state, sets status to FILLED.
            - Raises an error if standing quantity becomes negative.
        """
        if quantity <= 0 or self._payload["status"] not in (
            OrderStatus.PENDING,
            OrderStatus.PARTIALLY_FILLED,
        ):
            return
        self._payload["standing_quantity"] -= quantity

        if self._payload["standing_quantity"] == 0:
            if self._payload["status"] == OrderStatus.PENDING:
                self._payload["status"] = OrderStatus.CANCELLED
                self._payload["closed_at"] = datetime.now()
            else:
                self._payload["status"] = OrderStatus.FILLED
        elif self._payload["standing_quantity"] < 0:
            raise RuntimeError("standing quantity has become < 0")

    def update_upnl(self, price: float) -> None:
        """
        Calculates and updates the unrealised PnL based on the `price`.

        If the position has an open quantity, this method computes unrealised PnL
        using the current price and updates the payload. Otherwise, sets unrealised PnL to 0.

        Args:
            price (float): The price used for PnL calculation.

        Side Effects:
            - Updates self._payload["unrealised_pnl"].
        """
        if self.open_quantity > 0:
            self._payload["unrealised_pnl"] = self._calculate_pnl(
                price, self.open_quantity
            )
        else:
            self._payload["unrealised_pnl"] = 0.0

    def _calculate_pnl(self, price: float, quantity: int) -> float:
        """
        Calculates profit or loss for a given quantity and execution price.
        """
        filled_price = self._payload["filled_price"]
        direction = -1 if self._payload["side"] == Side.ASK else 1
        return (price - filled_price) * quantity * direction

    def _calculate_filled_price(self) -> float:
        """
        Helper to calculate the volume-weighted average price.
        """
        if not self._filled_price:
            return 0.0

        return round(self._filled_price / self._filled_quantity, 2)
