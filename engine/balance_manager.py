from enums import Side
from .typing import BalanceUpdate


class BalanceManager:
    """
    Manages the open and standing quantities of
    and order. Acts as a centralised state machine.
    """
    def __init__(self) -> None:
        self._users: dict[str, int] = {}

    def append(self, user_id: str):
        self._users.setdefault(user_id, 0)
        
    def remove(self, user_id: str) -> None:
        self._users.pop(user_id, None)
        
    def get_balance(self, user_id: str) -> int | None:
        return self._users.get(user_id)

    def increase_balance(self, user_id: str, quantity: int):
        if user_id in self._users:
            self._users[user_id] += quantity

    def decrease_balance(self, user_id: str, quantity: int):
        if user_id in self._users:
            self._users[user_id] -= quantity