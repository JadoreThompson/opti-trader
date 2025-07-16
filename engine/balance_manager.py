from .typing import BalanceUpdate


class BalanceManager:
    """
    Manages the open and standing quantities of
    and order. Acts as a centralised state machine.
    """

    def __init__(self) -> None:
        self._payloads: dict[str, dict] = {}

    def append(self, payload: dict) -> None:
        """
        Appends to the manager. If the order id already
        exists raises error exclaiming it already exists.

        Args:
            payload (dict): Payload to append.

        Raises:
            ValueError: A payload with said order_id is already
                present in the manager.
        """
        order_id = payload["order_id"]
        if order_id in self._payloads:
            raise ValueError(f"{order_id} already exists.")

        self._payloads[order_id] = payload

    def remove(self, order_id: str) -> None:
        self._payloads.pop(order_id)

    def get(self, order_id: str) -> dict | None:
        """Returns the payload belonging to the passed `order_id`"""
        return self._payloads.get(order_id)

    def get_balance(self, order_id: str) -> BalanceUpdate | None:
        payload = self._payloads.get(order_id)
        if payload:
            return BalanceUpdate(payload["open_quantity"], payload["standing_quantity"])

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
        payload["standing_quantity"] -= quantity
        payload["open_quantity"] += quantity
        
        return BalanceUpdate(payload["open_quantity"], payload["standing_quantity"])

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

        return BalanceUpdate(payload["open_quantity"], payload["standing_quantity"])
