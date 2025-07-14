from config import PRODUCTION
from engine.spot_order import SpotOrder
from enums import OrderStatus, OrderType, Side
from .base_engine import BaseEngine
from ..enums import MatchOutcome, Tag
from ..order import Order
from ..orderbook import OrderBook
from ..spot_position import SpotPosition
from ..typing import MatchResult, CloseRequest, ModifyRequest


class SpotEngine(BaseEngine[SpotPosition]):
    def __init__(self):
        super().__init__(SpotPosition)

    def place_order(self, payload: dict) -> None:
        if payload["instrument"] not in self._orderbooks:
            if PRODUCTION:
                return
            self._orderbooks[payload["instrument"]] = OrderBook()

        exits_specified = (
            payload["take_profit"] is not None or payload["stop_loss"] is not None
        )
        ob = self._orderbooks[payload["instrument"]]

        order = SpotOrder(
            payload["order_id"],
            Tag.ENTRY,
            payload["side"],
            payload["quantity"],
            payload=payload,
        )

        if payload["order_type"] == OrderType.LIMIT:
            if not (  # Checking if not crossable
                order.side == Side.BID
                and ob.best_ask is not None
                and payload["limit_price"] >= ob.best_ask
            ) or (
                order.side == Side.ASK
                and ob.best_bid is not None
                and payload["limit_price"] <= ob.best_bid
            ):
                order.set_price(payload["limit_price"])
                ob.append(order, order.price)

                if exits_specified:
                    pos = self._position_manager.create(payload)
                    pos.entry_order = order
                return

        result: MatchResult = self._match(order, ob)

        if exits_specified:
            pos = self._position_manager.create(payload)

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            ob.set_price(result.price)

            if exits_specified:
                pos.apply_fill(result.quantity)
                self._place_tp_sl(pos, ob)
            else:
                order.apply_fill(result.quantity)

            order.filled_quantity = result.quantity

            if result.outcome == MatchOutcome.SUCCESS:
                return

        price = payload["limit_price"] or result.price or ob.price
        print(payload["limit_price"], result.price, ob.price)
        order.set_price(price)
        ob.append(order, order.price)

        if exits_specified:
            pos.entry_order = order

    def cancel_order(self, request: CloseRequest) -> None:
        return super().cancel_order(request)

    def modify_order(self, request: ModifyRequest) -> None:
        return super().modify_order(request)

    def _handle_filled_order(
        self,
        order: SpotOrder,
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
        if order.has_position:
            pos = self._position_manager.get(order.id)

        if order.tag == Tag.ENTRY:
            order.apply_fill(filled_quantity)
            ob.remove(order, order.price)

            if order.has_position:
                if pos.take_profit_order is not None or pos.stop_loss_order is not None:
                    self._mutate_tp_sl_quantity(pos)
                else:
                    self._place_tp_sl(pos, ob)
        else:
            order.apply_close(filled_quantity)
            if order.has_position:
                self._remove_tp_sl(pos, ob)
                if pos.status == OrderStatus.CLOSED:
                    self._position_manager.remove(pos.id)

    def _handle_touched_order(
        self,
        order: SpotOrder,
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
        if order.has_position:
            pos = self._position_manager.get(order.id)

        if order.tag == Tag.ENTRY:
            order.apply_fill(touched_quantity)

            if order.has_position:
                if pos.take_profit_order is not None or pos.stop_loss_order is not None:
                    self._mutate_tp_sl_quantity(pos)
                else:
                    self._place_tp_sl(pos, ob)
        else:
            order.apply_close(touched_quantity)
            if order.has_position:
                self._mutate_tp_sl_quantity(pos)

    def _place_tp_sl(self, pos: SpotPosition, ob: OrderBook) -> None:
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
            new_order.has_position = True
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
            new_order.has_position = True
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
        q = int((total_quantity * 0.1) // (max_price - min_price))
        liq_positions = []

        for i in range(1, int(max_price - min_price) + 1):
            pos = self._position_manager.create(
                {
                    "order_id": f"liquidity_{i}",
                    "instrument": instrument,
                    "status": OrderStatus.PENDING,
                    "side": Side.BID,
                    "quantity": q,
                    "standing_quantity": 0,
                    "open_quantity": q,
                    "filled_price": ob._starting_price,
                    "take_profit": max_price - i,
                    "stop_loss": max(1, i - 1),
                }
            )
            pos._payload["status"] = OrderStatus.FILLED
            self._place_tp_sl(pos, ob)
            liq_positions.append(pos)

        return liq_positions
