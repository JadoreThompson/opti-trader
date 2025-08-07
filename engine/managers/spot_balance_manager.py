from collections import defaultdict
from ..protocols import BalanceManagerProtocol


class SpotBalanceManager(BalanceManagerProtocol):
    """
    Manages the open and standing quantities of
    and order. Acts as a centralised state machine.
    """

    def __init__(self) -> None:
        self._balances: dict[str, int] = defaultdict(int)

    def append(self, db_payload: dict) -> None:
        self._balances[db_payload['user_id']] = 0

    def remove(self, db_payload: dict) -> None:
        self._balances.pop(db_payload["user_id"], None)

    def get_balance(self, db_payload: dict) -> None:
        return self._balances.get(db_payload["user_id"], 0)

    def increase_balance(self, db_payload: dict, quantity: int) -> None:
        self._balances[db_payload["user_id"]] += quantity

    def decrease_balance(self, db_payload: dict, quantity: int) -> None:
        self._balances[db_payload["user_id"]] -= quantity
