class BalanceManager:
    """
    Manages the open and standing quantities of
    and order. Acts as a centralised state machine.
    """

    def __init__(self) -> None:
        self._user_balances: dict[str, int] = {}

    def append(self, user_id: str):
        self._user_balances.setdefault(user_id, 0)

    def remove(self, user_id: str) -> None:
        self._user_balances.pop(user_id, None)

    def get_balance(self, user_id: str) -> int:
        return self._user_balances.get(user_id, 0)

    def increase_balance(self, user_id: str, quantity: int):
        if user_id in self._user_balances:
            self._user_balances[user_id] += quantity

    def decrease_balance(self, user_id: str, quantity: int):
        if user_id in self._user_balances:
            self._user_balances[user_id] -= quantity
