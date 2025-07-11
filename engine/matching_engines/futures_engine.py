from config import PRODUCTION
from enums import OrderStatus, OrderType, Side
from .base_engine import BaseEngine
from ..enums import MatchOutcome, Tag
from ..order import Order
from ..orderbook.orderbook import OrderBook
from ..position import Position
from ..typing import (
    MODIFY_DEFAULT,
    CloseRequest,
    CloseRequestQuantity,
    MatchResult,
    ModifyRequest,
)


class FuturesEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__()

    def place_order(self, payload: dict) -> None:
        if payload["instrument"] not in self._orderbooks:
            if PRODUCTION:
                return
            self._orderbooks[payload["instrument"]] = OrderBook()

        ob = self._orderbooks[payload["instrument"]]
        pos = self._position_manager.create(payload)
        order = Order(pos.id, Tag.ENTRY, payload["side"], payload["quantity"])
        order.payload = payload

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
                pos.entry_order = order
                return

        result: MatchResult = self._match(order, ob)

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            ob.set_price(result.price)
            self._place_tp_sl(pos, ob)
            pos.apply_entry_fill(result.quantity, result.price)

            if result.outcome == MatchOutcome.SUCCESS:
                return

        price = payload["limit_price"] or result.price or ob.price
        order.set_price(price)
        ob.append(order, price)
        pos.entry_order = order

    def close_order(self, request: CloseRequest):
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

    def cancel_order(self, request: CloseRequest):
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

    def modify_order(self, request: ModifyRequest):
        pos = self._position_manager.get(request.order_id)
        ob = self._orderbooks[pos.instrument]
        payload = pos.payload

        if request.limit_price != MODIFY_DEFAULT:
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

        if request.take_profit != MODIFY_DEFAULT:
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

        if request.stop_loss != MODIFY_DEFAULT:
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

    def _handle_filled_orders(
        self, orders: list[tuple[Order, int]], price: float, ob: OrderBook
    ):
        for order, filled_quantity in orders:
            pos = self._position_manager.get(order.id)

            if order.tag == Tag.ENTRY:
                pos.apply_entry_fill(filled_quantity, price)

                if pos.take_profit_order is not None or pos.stop_loss_order is not None:
                    self._mutate_tp_sl_quantity(pos)
                else:
                    self._place_tp_sl(pos, ob)

                ob.remove(order, order.price)
            else:
                pos.apply_close(filled_quantity, price)
                self._remove_tp_sl(pos, ob)

                if pos.status == OrderStatus.CLOSED:
                    self._position_manager.remove(pos.id)

    def _handle_touched_orders(
        self, orders: list[tuple[Order, int]], price: float, ob: OrderBook
    ):
        for order, touched_quantity in orders:
            print(order.payload)
            pos = self._position_manager.get(order.id)
            if pos.status == OrderStatus.CLOSED:
                raise RuntimeError("touched")

            if order.tag == Tag.ENTRY:
                pos.apply_entry_fill(touched_quantity, price)

                if pos.take_profit_order is not None or pos.stop_loss_order is not None:
                    self._mutate_tp_sl_quantity(pos)
                else:
                    self._place_tp_sl(pos, ob)
            else:
                pos.apply_close(touched_quantity, price)
                self._mutate_tp_sl_quantity(pos)

    def _place_tp_sl(self, pos: Position, ob: OrderBook):
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

    def _mutate_tp_sl_quantity(self, pos: Position):
        if pos.take_profit_order is not None:
            pos.take_profit_order.quantity = pos.open_quantity
            pos.take_profit_order.filled_quantity = 0
        if pos.stop_loss_order is not None:
            pos.stop_loss_order.quantity = pos.open_quantity
            pos.stop_loss_order.filled_quantity = 0

    def _remove_tp_sl(self, pos: Position, ob: OrderBook):
        if pos.take_profit_order is not None:
            ob.remove(pos.take_profit_order, pos.take_profit_order.price)
            pos.take_profit_order = None
        if pos.stop_loss_order is not None:
            ob.remove(pos.stop_loss_order, pos.stop_loss_order.price)
            pos.stop_loss_order = None

    def _validate_close_req_quantity(
        self, request_quantity: CloseRequestQuantity, base_quantity: int
    ):
        if request_quantity == "ALL":
            return base_quantity

        try:
            quantity = int(request_quantity)

            if quantity <= base_quantity:
                return quantity
        except TypeError:
            pass

        raise ValueError(f"Invalid request quantity {request_quantity}")
