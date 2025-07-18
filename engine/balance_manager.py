from enums import Side
from .typing import BalanceUpdate


class BalanceManager:
    """
    Manages the open and standing quantities of
    and order. Acts as a centralised state machine.
    """

    def __init__(self) -> None:
        self._payloads: dict[str, dict] = {}
        self._users: dict[str, int] = {}

    def append(self, payload: dict) -> bool:
        """
        Appends to the manager. If the order id already
        exists raises error exclaiming it already exists.

        Args:
            payload (dict): Payload to append.

        Returns:
            bool - True if successfull append else False if insufficient balance
                or order_id already existed.
        """
        order_id = payload["order_id"]
        user_id = payload["user_id"]

        if order_id in self._payloads:
            return False
        if payload["side"] == Side.ASK and payload["quantity"] > self._users.get(
            payload["user_id"], 0
        ):
            return False
        if user_id not in self._users:
            self._users[user_id] = 0

        self._payloads[order_id] = payload
        return True

    def remove(self, order_id: str) -> None:
        self._payloads.pop(order_id)

    def get(self, order_id: str) -> dict | None:
        """Returns the payload belonging to the passed `order_id`"""
        return self._payloads.get(order_id)

    def get_balance(self, order_id: str) -> BalanceUpdate | None:
        payload = self._payloads.get(order_id)
        if payload:
            return BalanceUpdate(
                payload["open_quantity"],
                payload["standing_quantity"],
                self._users[payload["user_id"]],
            )

    def increase_balance(self, order_id: str, quantity: int) -> BalanceUpdate:
        """
        Increases the open quantity and decreases the standing quantity
        for the order's payload and assigns the appropriate status value.
        Returns the new open and standing quantities.

        Args:
            order_id (str): Order ID of the order
            quantity (int): The quantity that just got filled.

        Raises:
            ValueError: quantity is less than 0

        Returns:
            BalanceUpdate: The new open and standing quantities.
        """
        if quantity <= 0:
            raise ValueError("Quantity must be greater than 0.")

        payload = self._payloads[order_id]
        payload['standing_quantity'] -= quantity
        payload["open_quantity"] += quantity
        self._users[payload["user_id"]] += quantity

        return BalanceUpdate(
            payload["open_quantity"],
            payload["standing_quantity"],
            self._users[payload["user_id"]],
        )

    def decrease_balance(self, order_id: str, quantity: int) -> BalanceUpdate:
        """
        Decreases the open quantity for the order and returns
        the new open and standing quantities.

        Args:
            order_id (str): Order ID of the order
            quantity (int): The quantity that just got filled.

        Raises:
            ValueError: quantity is less than 0

        Returns:
            BalanceUpdate: The new open and standing quantities.
        """
        if quantity <= 0:
            raise ValueError("Quantity must be greater than 0.")

        payload = self._payloads[order_id]
        payload["open_quantity"] -= quantity
        self._users[payload["user_id"]] -= quantity

        return BalanceUpdate(
            payload["open_quantity"],
            payload["standing_quantity"],
            self._users[payload["user_id"]],
        )

    def synchronise(self, payload: dict) -> None:
        if (
            payload["order_id"] not in self._payloads
            or payload["user_id"] not in self._users
        ):
            raise ValueError("Payload doesn't exist.")

        ex_payload = self._payloads[payload["order_id"]]
        prev_op_quantity = ex_payload["open_quantity"]
        ex_payload["standing_quantity"], ex_payload["open_quantity"] = (
            payload["standing_quantity"],
            payload["open_quantity"],
        )
        self._users[payload["user_id"]] += payload["open_quantity"] - prev_op_quantity
