from enums import OrderType, Side
from .base_engine import BaseEngine
from ..balance_manager import BalanceManager
from ..enums import MatchOutcome, Tag
from ..orders.oco_order import OCOOrder
from ..orders.spot_order import SpotOrder
from ..oco_manager import OCOManager
from ..orderbook import OrderBook
from ..order_manager import OrderManager
from ..typing import MatchResult, CloseRequest


class SpotEngine(BaseEngine[SpotOrder]):
    def __init__(
        self,
        oco_manager: OCOManager = None,
        balance_manager: BalanceManager = None,
        order_manager: OrderManager = None,
    ):
        super().__init__()
        self._oco_manager = oco_manager or OCOManager()
        self._balance_manager = balance_manager or BalanceManager()
        self._order_manager = order_manager or OrderManager()

    def place_order(self, payload: dict) -> None:
        """
        Places a new order in the engine. If the payload
        declares a take profit or stop loss price then an OCO order
        is placed internally, else the engine tries to match the order
        at the best opposite book price. If this fails the engine then
        places a limit order for the order.

        Args:
            payload (dict): Order details including instrument, side, quantity,
                type, and limit price.
        """
        ob = self._orderbooks.setdefault(payload["instrument"], OrderBook())
        self._balance_manager.append(payload)
        order = SpotOrder(
            payload["order_id"], Tag.ENTRY, payload["side"], payload["quantity"]
        )

        if payload["stop_loss"] is not None or payload["take_profit"] is not None:
            self._handle_place_oco_order(order, payload, ob)
            return

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
                self._order_manager.append(order)
                return

        result: MatchResult = self._match(order, ob)
        order.filled_quantity = result.quantity

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            ob.set_price(result.price)

            if order.side == Side.BID or (
                order.side == Side.ASK and order.tag == Tag.ENTRY
            ):
                self._balance_manager.increase_balance(
                    payload["order_id"], result.quantity
                )
            else:
                self._balance_manager.decrease_balance(
                    payload["order_id"], result.quantity
                )

            if result.outcome == MatchOutcome.SUCCESS:
                self._balance_manager.remove(payload["order_id"])
                return

        price = payload["limit_price"] or result.price or ob.price
        order.set_price(price)
        ob.append(order, price)
        self._order_manager.append(order)

    def cancel_order(self, request: CloseRequest) -> None:
        """Cancel or reduce an existing order.

        Reduces the standing quantity of an order. If the standing quantity is
        already zero, the method returns without changes. Handles order book
        removal and OCO cleanup when the order is fully closed.

        Args:
            request (CloseRequest): Close request containing order parameters.
        """

        order = self._order_manager.get(request.order_id)
        payload = self._balance_manager.get(order.id)
        ob = self._orderbooks[payload["instrument"]]

        if payload["standing_quantity"] == 0:
            return

        standing_quantity = payload["standing_quantity"]
        requested_quantity = self._validate_close_req_quantity(
            request.quantity, standing_quantity
        )
        remaining_quantity = standing_quantity - requested_quantity
        payload["standing_quantity"] = remaining_quantity
        entry_in_book = order.quantity != order.filled_quantity
        order.quantity -= remaining_quantity

        if remaining_quantity == 0:
            if entry_in_book:
                ob.remove(order, order.price)

            if payload["open_quantity"] == 0 and order.oco_id is not None:
                self._remove_tp_sl(self._oco_manager.get(order.oco_id), ob)
                self._oco_manager.remove(order.oco_id)

            self._balance_manager.remove(order.id)
            self._order_manager.remove(order.id)

    def _handle_place_oco_order(
        self, order: SpotOrder, payload: dict, ob: OrderBook[SpotOrder]
    ) -> None:
        """
        Place an order with OCO (One-Cancels-Other) handling.

        Attempts to place the order into the order book. If immediately
        matchable, performs matching and updates balances. Otherwise, assigns
        an OCO ID, appends the order, and sets take-profit/stop-loss legs.

        Args:
            order (SpotOrder): The primary spot order to place.
            payload (dict): Associated order parameters and metadata.
            ob (OrderBook[SpotOrder]): Target order book for placement.
        """
        oco_order: OCOOrder = self._oco_manager.create()
        payload["oco_id"] = oco_order.id  # Only assigning during tests

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
                order.set_oco_id(oco_order.id)
                oco_order.leg_a = order
                self._order_manager.append(order)
                return

        result: MatchResult = self._match(order, ob)
        order.filled_quantity = result.quantity

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            ob.set_price(result.price)
            self._balance_manager.increase_balance(payload["order_id"], result.quantity)
            self._place_tp_sl(oco_order, ob)

            if result.outcome == MatchOutcome.SUCCESS:
                return

        price = payload["limit_price"] or result.price or ob.price
        order.set_price(price)
        ob.append(order, price)
        order.set_oco_id(oco_order.id)
        oco_order.leg_a = order
        self._order_manager.append(order)

    def _handle_filled_order(
        self,
        order: SpotOrder,
        filled_quantity: int,
        price: float,
        ob: OrderBook[SpotOrder],
    ) -> None:
        """
        Handle a fully or partially filled order.

        Updates balances and cleans up the order book or OCO legs as needed.
        For entry orders, may trigger placement or mutation of TP/SL legs.
        For exit orders, may remove OCO entries when quantities reach zero.

        Args:
            order (SpotOrder): The order that was filled.
            filled_quantity (int): Quantity filled in this match.
            price (float): Execution price.
            ob (OrderBook[SpotOrder]): Order book containing the order.
        """
        # TODO: Open it up for different order_id OCO orders.
        if order.side == Side.BID or (
            order.side == Side.ASK and order.tag == Tag.ENTRY
        ):
            balance_update = self._balance_manager.increase_balance(
                order.id, filled_quantity
            )
        else:
            balance_update = self._balance_manager.decrease_balance(
                order.id, filled_quantity
            )

        if order.tag == Tag.ENTRY:
            ob.remove(order, order.price)

            if order.oco_id is not None:
                oco_order = self._oco_manager.get(order.oco_id)
                if oco_order.leg_b is None and oco_order.leg_c is None:
                    self._place_tp_sl(oco_order, ob)
                else:
                    self._mutate_tp_sl(
                        self._oco_manager.get(order.oco_id),
                        balance_update.open_quantity,
                    )
            else:
                self._balance_manager.remove(order.id)
                self._order_manager.remove(order.id)
        else:
            oco_order = self._oco_manager.get(order.oco_id)
            self._remove_tp_sl(oco_order, ob)

            if (
                balance_update.open_quantity == 0
                and balance_update.standing_quantity == 0
            ):
                self._oco_manager.remove(oco_order.id)
                self._balance_manager.remove(order.id)
                self._order_manager.remove(order.id)

    def _handle_touched_order(
        self,
        order: SpotOrder,
        filled_quantity: int,
        price: float,
        ob: OrderBook[SpotOrder],
    ) -> None:
        """
        Handle an order that was partially executed (touched).

        Updates balance state and may place or adjust TP/SL legs for the
        associated OCO order.

        Args:
            order (SpotOrder): The order that was touched.
            filled_quantity (int): Quantity executed.
            price (float): Execution price.
            ob (OrderBook[SpotOrder]): Order book containing the order.
        """

        if order.side == Side.BID or (
            order.side == Side.ASK and order.tag == Tag.ENTRY
        ):
            balance_update = self._balance_manager.increase_balance(
                order.id, filled_quantity
            )
        else:
            balance_update = self._balance_manager.decrease_balance(
                order.id, filled_quantity
            )

        if (
            order.oco_id is not None
        ):  # TODO: Open it up for different order_id OCO orders.
            oco_order = self._oco_manager.get(order.oco_id)
            if oco_order.leg_b is None and oco_order.leg_c is None:
                self._place_tp_sl(oco_order, ob)
            else:
                self._mutate_tp_sl(
                    self._oco_manager.get(order.oco_id), balance_update.open_quantity
                )

    def _place_tp_sl(self, oco_order: OCOOrder, ob: OrderBook[SpotOrder]) -> None:
        """
        Place take-profit and stop-loss orders for an OCO order.

        Creates and appends TP and/or SL orders based on the payload linked
        to the entry order.

        Args:
            oco_order (OCOOrder): OCO container for the TP/SL legs.
            ob (OrderBook[SpotOrder]): Order book for appending the TP/SL orders.
        """
        entry_order = oco_order.leg_a
        payload = self._balance_manager.get(entry_order.id)

        if payload["stop_loss"] is not None:
            new_order = SpotOrder(
                payload["order_id"],
                Tag.STOP_LOSS,
                Side.ASK,
                payload["open_quantity"],
                payload["stop_loss"],
                oco_id=oco_order.id,
            )
            ob.append(new_order, new_order.price)
            oco_order.leg_b = new_order

        if payload["take_profit"] is not None:
            new_order = SpotOrder(
                payload["order_id"],
                Tag.TAKE_PROFIT,
                Side.ASK,
                payload["open_quantity"],
                payload["take_profit"],
                oco_id=oco_order.id,
            )
            ob.append(new_order, new_order.price)
            oco_order.leg_c = new_order

    def _mutate_tp_sl(self, oco_order: OCOOrder, open_quantity: int) -> None:
        """Update quantities of TP and SL legs in an OCO order.

        Args:
            oco_order (OCOOrder): OCO container holding TP/SL legs.
            open_quantity (int): New open quantity to apply.
        """
        if oco_order.leg_b is not None:
            oco_order.leg_b.quantity = open_quantity
        if oco_order.leg_c is not None:
            oco_order.leg_c.quantity = open_quantity

    def _remove_tp_sl(self, oco_order: OCOOrder, ob: OrderBook[SpotOrder]) -> None:
        """Remove TP and SL orders from an OCO order.

        Cleans up associated TP/SL legs from the order book and clears them
        from the OCO container.

        Args:
            oco_order (OCOOrder): OCO container holding TP/SL legs.
            ob (OrderBook[SpotOrder]): Order book from which to remove the legs.
        """
        if oco_order.leg_b is not None:
            ob.remove(oco_order.leg_b, oco_order.leg_b.price)
            oco_order.leg_b = None
        if oco_order.leg_c is not None:
            ob.remove(oco_order.leg_c, oco_order.leg_c.price)
            oco_order.leg_c = None
