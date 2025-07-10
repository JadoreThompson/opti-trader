from collections import defaultdict
from datetime import datetime
import pprint
from enums import OrderStatus, Side
from .enums import Tag
from .order import Order


class Position:
    def __init__(
        self,
        payload: dict,
        entry_order: Order | None = None,
        stop_loss: Order | None = None,
        take_profit: Order | None = None,
    ) -> None:
        self._payload = payload
        self._instrument = payload["instrument"]
        self._entry_order = entry_order or Order(self, Tag.ENTRY, payload["side"])
        self.stop_loss_order = stop_loss
        self.take_profit_order = take_profit
        self._filled_quantity: int = 0
        self._quantity: int = None
        self._filled_prices: dict[float, int] = defaultdict(int)
        self._filled_price: float = None

    # def reduce_standing_quantity(self, price: float, quantity: int) -> None:
    #     # print(locals())
    #     standing_qty = self._payload["standing_quantity"]

    #     if quantity > standing_qty:
    #         raise ValueError(
    #             f"{quantity} is greater than standing quantity {standing_qty}"
    #         )
    #     elif quantity == 0:
    #         return

    #     remaining_qty = standing_qty - quantity
    #     status: OrderStatus = self._payload["status"]

    #     if status in (OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED):
    #         self._filled_prices[price] += quantity

    #     if remaining_qty > 0:
    #         if status == OrderStatus.PENDING:
    #             self._payload["status"] = OrderStatus.PARTIALLY_FILLED
    #         elif status == OrderStatus.FILLED:
    #             self._payload["status"] = OrderStatus.PARTIALLY_CLOSED
    #     elif status in (OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED):
    #         self._payload["status"] = OrderStatus.FILLED
    #     else:
    #         self._payload["status"] = OrderStatus.CLOSED

    #     self._payload["standing_quantity"] = remaining_qty

    def reduce_standing_quantity(self, price: float, quantity: int) -> None:
        # print(
        #     f"\n[reduce_standing_quantity] Called with price={price}, quantity={quantity}"
        # )

        standing_qty = self._payload["standing_quantity"]
        # print(f"[reduce_standing_quantity] Current standing_quantity: {standing_qty}")

        if quantity > standing_qty:
            raise ValueError(
                f"[reduce_standing_quantity] Error: {quantity} is greater than standing quantity {standing_qty}"
            )
        elif quantity == 0:
            # print("[reduce_standing_quantity] No quantity to reduce. Exiting early.")
            return

        remaining_qty = standing_qty - quantity
        status: OrderStatus = self._payload["status"]
        # print(f"[reduce_standing_quantity] Order status before update: {status}")
        # print(
        #     f"[reduce_standing_quantity] Remaining quantity after reduction: {remaining_qty}"
        # )

        # Update filled prices

        if status in (OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED):
            self._filled_prices[price] += quantity

            self._payload["filled_price"] = self._calculate_filled_price(
                self._payload["quantity"] - remaining_qty
            )
            # print(
            #     f"[reduce_standing_quantity] Updated filled_prices[{price}] = {self._filled_prices[price]}"
            # )

        # Determine new status
        if remaining_qty > 0:
            if status == OrderStatus.PENDING:
                self._payload["status"] = OrderStatus.PARTIALLY_FILLED
            elif status == OrderStatus.FILLED:
                self._payload["status"] = OrderStatus.PARTIALLY_CLOSED
        elif status in (OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED):
            self._payload["status"] = OrderStatus.FILLED
        else:
            self._payload["status"] = OrderStatus.CLOSED

        # print(
        #     f"[reduce_standing_quantity] Updated order status: {self._payload['status']}"
        # )

        # Update standing quantity
        self._payload["standing_quantity"] = remaining_qty
        # print(
        #     f"[reduce_standing_quantity] Updated standing_quantity: {self._payload['standing_quantity']}"
        # )

    def set_filled(self) -> None:
        self._payload["status"] = OrderStatus.FILLED
        self._payload["standing_quantity"] = self._payload["quantity"]
        # pprint.pprint(self._payload)
        self._payload["filled_price"] = self._calculate_filled_price(
            self._payload["quantity"]
        )

        self._entry_order = None

    def set_filled_by_cancel(
        self,
    ) -> None:
        self._payload["status"] = OrderStatus.FILLED
        self._quantity = self._payload["quantity"] - self._payload["standing_quantity"]
        self._payload["standing_quantity"] = self._quantity
        self._filled_price = self._calculate_filled_price(self._quantity)
        self._entry_order = None

    def set_closed(self, close_price: float) -> None:
        self._payload["status"] = OrderStatus.CLOSED
        self._payload["closed_at"] = datetime.now()
        self._payload["closed_price"] = close_price
        self._payload["standing_quantity"] = 0
        self._payload["unrealised_pnl"] = 0.0

        self.stop_loss_order = None
        self.take_profit_order = None

    def update_upnl(self, current_price: float) -> None:
        if self._payload["status"] == OrderStatus.PENDING:
            raise ValueError("Fill some quantity first. status is pending.")

        self._payload["unrealised_pnl"] = self._calculate_pnl(
            current_price, self._payload["standing_quantity"]
        )

    def update_rpnl(self, price: float, quantity: int):
        """Makes the assumption you've already called reduce_standing_quantity"""
        self._payload["realised_pnl"] += self._calculate_pnl(price, quantity)
        self._payload["unrealised_pnl"] = self._calculate_pnl(
            price, self._payload["standing_quantity"]
        )

    def _calculate_pnl(self, current_price: float, quantity: int):
        filled_price = self._payload["filled_price"]
        direction = -1 if self._payload["side"] == Side.ASK else 1
        return (current_price - filled_price) * quantity * direction

    def _calculate_filled_price(self, quantity: int) -> float:
        # qty: int = self._payload["quantity"]
        return round(
            sum(price * qty for price, qty in self._filled_prices.items()) / quantity, 2
        )

    @property
    def id(self):
        return self._payload["order_id"]

    @property
    def instrument(self) -> str:
        return self._instrument

    @property
    def entry_order(self) -> Order:
        return self._entry_order

    @property
    def quantity(self) -> int:
        return self._quantity or self._payload["quantity"]

    @property
    def standing_quantity(self) -> int:
        return self._payload["standing_quantity"]

    @property
    def status(self) -> OrderStatus:
        return self._payload["status"]

    @status.setter
    def status(self, value: OrderStatus) -> None:
        self._payload["status"] = value

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        return f"Position(order=({self.entry_order}), sl=({self.stop_loss_order}), tp=({self.take_profit_order}))"
