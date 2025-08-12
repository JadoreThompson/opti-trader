from collections import defaultdict


class BalanceManager:
    """
    Manages the total asset holdings for a user
    """

    def __init__(self) -> None:
        self._balances: dict[str, int] = defaultdict(int)

    def append(self, user_id: str) -> None:
        self._balances[user_id] = 0

    def remove(self, user_id: dict) -> None:
        self._balances.pop(user_id, None)

    def get_balance(self, user_id: str) -> None:
        return self._balances.get(user_id, 0)

    def increase_balance(self, user_id: str, quantity: int) -> None:
        self._balances[user_id] += quantity

    def decrease_balance(self, user_id: str, quantity: int) -> None:
        self._balances[user_id] -= quantity
