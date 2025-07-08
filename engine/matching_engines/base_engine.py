from typing import Iterable, TypedDict, List, overload

from enums import Side
from ..enums import MatchOutcome
from ..order import Order
from ..orderbook.orderbook import OrderBook
from ..position_manager import PositionManager
from ..typing import MatchResult, ClosePayload


class CancelOrderPayload(TypedDict):
    order_id: str
    instrument: str


class BaseEngine:
    def __init__(
        self,
    ) -> None:
        self._order_books: dict[str, OrderBook] = {}
        self._position_manager = PositionManager()

    def run(self, instruments: List[str]) -> None:
        """Initializes the engine"""
        for instr in instruments:
            self._order_books[instr] = OrderBook()

    @overload
    def place_order(self, payload: dict) -> None: ...
    
    @overload
    def close_order(self, payload: ClosePayload) -> None: ...
    
    @overload
    async def _listen(self) -> None: ...

    def _match(self, order: Order, ob: OrderBook) -> MatchResult:
        """
        Matches order against opposing book

        Args:
            order (dict)
            order_side (Side)
            ob (Orderbook): orderbook
            price (float): price to target

        Returns:
            MatchResult:
                Filled: (2, price)
                Partially filled: (1, price)
                Not filled: (0, None)
        """
        book_to_match = "asks" if order.side == Side.BID else "bids"
        aggresive_payload = order.payload
        starting_quantity = aggresive_payload["standing_quantity"]

        target_price = ob.best_ask if order.side == Side.BID else ob.best_bid
        if target_price is None:
            return MatchResult(MatchOutcome.FAILURE, None)

        touched_orders: list[Order] = []
        filled_orders: list[tuple[Order, int]] = []

        for resting_order in ob.get_orders(target_price, book_to_match):
            if aggresive_payload["standing_quantity"] == 0:
                break

            if resting_order == order:  # Self match prevention.
                continue

            og_resting_qty = resting_order.payload["standing_quantity"]
            match_qty = min(og_resting_qty, aggresive_payload["standing_quantity"])

            resting_order.payload["standing_quantity"] -= match_qty
            aggresive_payload["standing_quantity"] -= match_qty

            if resting_order.payload["standing_quantity"] == 0:
                filled_orders.append((resting_order, og_resting_qty))
            else:
                touched_orders.append((resting_order, og_resting_qty))

        self._handle_touched_orders(touched_orders, filled_orders, target_price)
        self._handle_filled_orders(filled_orders, target_price, ob)

        if aggresive_payload["standing_quantity"] == 0:
            return MatchResult(MatchOutcome.SUCCESS, target_price)
        if aggresive_payload["standing_quantity"] == starting_quantity:
            return MatchResult(MatchOutcome.FAILURE, None)
        return MatchResult(MatchOutcome.PARTIAL, target_price)

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
