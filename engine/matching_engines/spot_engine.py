from enums import OrderType, Side
from .base_engine import BaseEngine
from ..balance_manager import BalanceManger
from ..enums import MatchOutcome, Tag
from ..oco_manager import OCOManager
from ..orderbook import OrderBook
from ..orders.oco_order import OCOOrder
from ..orders.spot_order import SpotOrder
from ..typing import MatchResult, CloseRequest, ModifyRequest


class SpotEngine(BaseEngine[SpotOrder]):
    def __init__(
        self, oco_manager: OCOManager = None, balance_manager: BalanceManger = None
    ):
        super().__init__()
        self._oco_manager = oco_manager or OCOManager()
        self._balance_manager = balance_manager or BalanceManger()

    def place_order(self, payload: dict) -> None:
        # Remove in PROD
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
                return

        result: MatchResult = self._match(order, ob)

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            ob.set_price(result.price)

            if order.side == Side.BID:
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

        order.filled_quantity = result.quantity
        price = payload["limit_price"] or result.price or ob.price
        order.set_price(price)
        ob.append(order, price)

    def _handle_place_oco_order(
        self, order: SpotOrder, payload: dict, ob: OrderBook[SpotOrder]
    ) -> None:
        oco_order: OCOOrder = self._oco_manager.create()

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
                return

        result: MatchResult = self._match(order, ob)

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            ob.set_price(result.price)
            self._balance_manager.increase_balance(payload["order_id"], result.quantity)
            self._place_tp_sl(oco_order, ob)

            if result.outcome == MatchOutcome.SUCCESS:
                return

        order.filled_quantity = result.quantity
        price = payload["limit_price"] or result.price or ob.price
        order.set_price(price)
        ob.append(order, price)
        order.set_oco_id(oco_order.id)
        oco_order.leg_a = order

    def _handle_filled_order(
        self,
        order: SpotOrder,
        filled_quantity: int,
        price: float,
        ob: OrderBook[SpotOrder],
    ) -> None:
        # TODO: Open it up for different order_id OCO orders.
        if order.side == Side.BID:
            print(1)
            balance_update = self._balance_manager.increase_balance(
                order.id, filled_quantity
            )
        else:
            self._balance_manager.decrease_balance(order.id, filled_quantity)

        print(order.id)
        print(balance_update)

        if order.tag == Tag.ENTRY:
            print(2)
            ob.remove(order, order.price)

            if order.oco_id is not None:
                oco_order = self._oco_manager.get(order.oco_id)
                print(order.id)
                if oco_order.leg_a is None and oco_order.leg_b is None:
                    print(3)
                    self._place_tp_sl(oco_order, ob)
                else:
                    print(4)
                    self._mutate_tp_sl(
                        self._oco_manager.get(order.oco_id),
                        balance_update.open_quantity,
                    )
            else:
                print(5)
                self._balance_manager.remove(order.id)
            if order.id == "buy1":
                raise RuntimeError()
        else:
            oco_order = self._oco_manager.get(order.oco_id)
            self._remove_tp_sl(oco_order, ob)
            self._oco_manager.remove(oco_order.id)

    def _handle_touched_order(
        self,
        order: SpotOrder,
        filled_quantity: int,
        price: float,
        ob: OrderBook[SpotOrder],
    ) -> None:
        if order.side == Side.BID:
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

    def _place_tp_sl(self, oco_order: OCOOrder, ob: OrderBook) -> None:
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
        if oco_order.leg_b is not None:
            oco_order.leg_b.quantity = open_quantity
        if oco_order.leg_c is not None:
            oco_order.leg_c.quantity = open_quantity

    def _remove_tp_sl(self, oco_order: OCOOrder, ob: OrderBook) -> None:
        if oco_order.leg_b is not None:
            ob.remove(oco_order.leg_b, oco_order.leg_b.price)
            oco_order.leg_b = None
        if oco_order.leg_c is not None:
            ob.remove(oco_order.leg_c, oco_order.leg_c.price)
            oco_order.leg_c = None
