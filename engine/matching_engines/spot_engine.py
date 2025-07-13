from config import PRODUCTION
from engine.typing import CloseRequest, ModifyRequest
from enums import OrderStatus, OrderType, Side
from .base_engine import BaseEngine
from ..enums import MatchOutcome, Tag
from ..order import Order
from ..orderbook import OrderBook
from ..position import Position
from ..typing import MatchResult


class SpotEngine(BaseEngine):
    def __init__(self):
        super().__init__()

    def place_order(self, payload: dict) -> None:
        if payload["instrument"] not in self._orderbooks:
            if PRODUCTION:
                return
            self._orderbooks[payload["instrument"]] = OrderBook()
            self._populate_book(ob, payload['instrument'], 1_000_000)

        ob = self._orderbooks[payload["instrument"]]
        pos = self._position_manager.create(payload)
        order = Order(pos.id, Tag.ENTRY, Side.BID, payload["quantity"])

        if payload["order_type"] == OrderType.LIMIT:
            # Checking if we're crossable
            if ob.best_ask is not None and payload["limit_price"] >= ob.best_ask:
                order.set_price(payload["limit_price"])
                ob.append(order, order.price)
                pos.entry_order = order
                return

        result: MatchResult = self._match(order, ob)

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            ob.set_price(result.price)
            self._place_tp_sl(pos, ob)
            pos.apply_entry_fill(result.quantity, result.price)
            order.filled_quantity = result.quantity

            if result.outcome == MatchOutcome.SUCCESS:
                return

    def close_order(self, request: CloseRequest) -> None:
        return super().close_order(request)

    def cancel_order(self, request: CloseRequest) -> None:
        return super().cancel_order(request)

    def modify_order(self, request: ModifyRequest) -> None:
        return super().modify_order(request)

    def _place_tp_sl(self, pos: Position, ob: OrderBook) -> None:
        """
        Places take-profit and stop-loss orders for a position if specified.

        Args:
            pos (Position): The position to attach exit orders to.
            ob (OrderBook): Order book for the position's instrument.
        """
        payload = pos.payload

        if payload["take_profit"] is not None:
            new_order = Order(
                pos.id,
                Tag.TAKE_PROFIT,
                Side.ASK,
                pos.open_quantity,
                payload["take_profit"],
            )
            pos.take_profit_order = new_order
            ob.append(new_order, new_order.price)

        if payload["stop_loss"] is not None:
            new_order = Order(
                pos.id,
                Tag.STOP_LOSS,
                Side.ASK,
                pos.open_quantity,
                payload["stop_loss"],
            )
            pos.stop_loss_order = new_order
            ob.append(new_order, new_order.price)

    def _populate_book(
        self, ob: OrderBook, instrument: str, total_quantity: int
    ) -> None:
        """
        Generates a batch of positions that act as initial liquidity
        for the book.

        Args:
            ob (OrderBook): Unpopulated, newly initialised book.
            instrument (str): Instrument the ob belongs to.
            total_quantity (int): Total quantity of shares avaialble in
                the book
        """

        if ob.bids or ob.asks:
            return

        min_price = 1.0
        max_price = ob._starting_price * 2
        q = (total_quantity * 0.1) // (max_price - min_price)

        for i in range(1, int(max_price - min_price) + 1):
            pos = self._position_manager.create(
                {
                    "order_id": f"liquidity_{i}",
                    "instrument": instrument,
                    "status": OrderStatus.FILLED,
                    "side": Side.ASK,
                    "quantity": q,
                    "standing_quantity": 0,
                    "open_quantity": q,
                    "filled_price": ob._starting_price,
                    "unrealised_pnl": 0.0,
                    "realised_pnl": 0.0,
                    "take_profit": i,
                    "stop_loss": max_price - i,
                }
            )
            self._place_tp_sl(pos, ob)
