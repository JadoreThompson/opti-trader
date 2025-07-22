from config import PRODUCTION
from enums import OrderStatus, OrderType, Side
from .base_engine import BaseEngine
from ..enums import MatchOutcome, Tag
from ..orderbook import OrderBook
from ..orders import Order
from ..position import Position
from ..position_manager import PositionManager
from ..typing import (
    MODIFY_SENTINEL,
    CloseRequest,
    MatchResult,
    ModifyRequest,
)


class FuturesEngine(BaseEngine[Order]):
    def __init__(self, loop=None) -> None:
        super().__init__(loop)
        self._position_manager = PositionManager()

    def place_order(self, payload: dict) -> None:
        """
        Places a new order in the futures engine.

        Creates an entry order and attempts to match it against the order book.
        If not immediately filled, the order is added to the book. Handles
        take-profit and stop-loss setup.

        Args:
            payload (dict): Order details including instrument, side, quantity,
                type, and limit price.
        """
        if payload["instrument"] not in self._orderbooks:
            if PRODUCTION:
                return
            self._orderbooks[payload["instrument"]] = OrderBook()

        ob = self._orderbooks[payload["instrument"]]
        pos = self._position_manager.create(payload)
        order = Order(pos.id, Tag.ENTRY, payload["side"], payload["quantity"])

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
                # order.set_price(payload["limit_price"])
                order.price = payload["limit_price"]
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

        price = payload["limit_price"] or result.price or ob.price
        # order.set_price(price)
        order.price = price
        ob.append(order, price)
        pos.entry_order = order

    def close_order(self, request: CloseRequest) -> None:
        """
        Closes an existing position based on the provided request.

        Attempts to match the opposing side of the order to close it, updating
        the position and cleaning up TP/SL orders if fully closed.

        Args:
            request (CloseRequest): Request specifying the order ID and quantity
                to close.
        """
        pos = self._position_manager.get(request.order_id)

        if pos.status == OrderStatus.PENDING:
            return

        ob = self._orderbooks[pos.instrument]
        requested_qty = self._validate_close_req_quantity(
            request.quantity, pos.open_quantity
        )
        open_quantity = pos.open_quantity
        dummy = Order(
            pos.id,
            Tag.ENTRY,
            Side.BID if pos.payload["side"] == Side.ASK else Side.ASK,
            requested_qty,
        )

        result: MatchResult = self._match(dummy, ob)

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            ob.set_price(result.price)
            pos.apply_close(result.quantity, result.price)

            if result.outcome == MatchOutcome.SUCCESS:
                if requested_qty == open_quantity:
                    self._remove_tp_sl(pos, ob)
                    self._position_manager.remove(pos.id)
                    return

            self._mutate_tp_sl_quantity(pos)

    def cancel_order(self, request: CloseRequest) -> None:
        """
        Cancels a pending or partially filled order.

        Cancels the requested quantity, updates position and order book, and
        removes the order if fully cancelled or filled.

        Args:
            request (CloseRequest): Request with order ID and quantity to cancel.
        """
        pos = self._position_manager.get(request.order_id)
        ob = self._orderbooks[pos.instrument]
        requested_quantity = self._validate_close_req_quantity(
            request.quantity, pos.standing_quantity
        )

        pos.apply_cancel(requested_quantity)
        if pos.status == OrderStatus.CANCELLED:
            ob.remove(pos.entry_order, pos.entry_order.price)
            self._position_manager.remove(pos.id)
        elif pos.status == OrderStatus.FILLED:
            if pos.entry_order is not None:
                ob.remove(pos.entry_order, pos.entry_order.price)

    def modify_order(self, request: ModifyRequest) -> None:
        """
        Modifies an existing order's limit price, take-profit, or stop-loss.

        Updates order parameters and the order book accordingly, only applying
        changes allowed by the current order status.

        Args:
            request (ModifyRequest): Contains modifications like new limit price,
                TP, or SL.
        """
        pos = self._position_manager.get(request.order_id)
        ob = self._orderbooks[pos.instrument]
        payload = pos.payload

        if request.limit_price != MODIFY_SENTINEL:
            if pos.status == OrderStatus.PENDING:
                payload["limit_price"] = request.limit_price
                order = pos.entry_order
                ob.remove(order, order.price)
                new_order = Order(
                    pos.id,
                    Tag.ENTRY,
                    pos.payload["side"],
                    pos.standing_quantity,
                    request.limit_price,
                )
                ob.append(new_order, new_order.price)
                pos.entry_order = new_order

        opposite_side = Side.BID if payload["side"] == Side.ASK else Side.BID

        if request.take_profit != MODIFY_SENTINEL:
            payload["take_profit"] = request.take_profit

            if pos.status != OrderStatus.PENDING:
                tp_order = pos.take_profit_order

                if tp_order is not None:
                    ob.remove(tp_order, tp_order.price)

                if request.take_profit is not None:
                    tp_order = tp_order or Order(
                        pos.id,
                        Tag.TAKE_PROFIT,
                        opposite_side,
                        pos.open_quantity,
                        request.take_profit,
                    )
                    pos.take_profit_order = tp_order
                else:
                    pos.take_profit_order = None

        if request.stop_loss != MODIFY_SENTINEL:
            payload["stop_loss"] = request.stop_loss

            if pos.status != OrderStatus.PENDING:
                sl_order = pos.stop_loss_order

                if sl_order is not None:
                    ob.remove(sl_order, sl_order.price)

                if request.stop_loss is not None:
                    sl_order = sl_order or Order(
                        pos.id,
                        Tag.STOP_LOSS,
                        opposite_side,
                        pos.open_quantity,
                        request.stop_loss,
                    )
                    pos.stop_loss_order = sl_order
                else:
                    pos.stop_loss_order = None

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

    def _place_tp_sl(self, pos: Position, ob: OrderBook) -> None:
        """
        Places take-profit and stop-loss orders for a position if specified.

        Args:
            pos (Position): The position to attach exit orders to.
            ob (OrderBook): Order book for the position's instrument.
        """
        payload = pos.payload
        exit_side = Side.BID if payload["side"] == Side.ASK else Side.ASK

        if payload["take_profit"] is not None:
            new_order = Order(
                pos.id,
                Tag.TAKE_PROFIT,
                exit_side,
                pos.open_quantity,
                payload["take_profit"],
            )
            pos.take_profit_order = new_order
            ob.append(new_order, new_order.price)

        if payload["stop_loss"] is not None:
            new_order = Order(
                pos.id,
                Tag.STOP_LOSS,
                exit_side,
                pos.open_quantity,
                payload["stop_loss"],
            )
            pos.stop_loss_order = new_order
            ob.append(new_order, new_order.price)

    def _mutate_tp_sl_quantity(self, pos: Position) -> None:
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

    def _remove_tp_sl(self, pos: Position, ob: OrderBook[Order]) -> None:
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
