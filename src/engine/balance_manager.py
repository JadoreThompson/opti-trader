from multiprocessing.queues import Queue as MPQueue

from config import REDIS_CLIENT, CASH_BALANCE_HKEY, CASH_ESCROW_HKEY
from utils.utils import get_instrument_balance_hkey, get_instrument_escrows_hkey


class BalanceManager:
    """
    Used as an in memory database for cash and asset balances with escrow tracking.
    """

    queue: MPQueue | None = None

    @classmethod
    def get_user_balance(cls, user_id: str) -> float:
        """Return available cash balance = balance - escrow."""
        balance = REDIS_CLIENT.hget(CASH_BALANCE_HKEY, user_id)
        escrow = REDIS_CLIENT.hget(CASH_ESCROW_HKEY, user_id)

        if balance is None:
            REDIS_CLIENT.hset(CASH_BALANCE_HKEY, user_id, 0)
        if escrow is None:
            REDIS_CLIENT.hset(CASH_ESCROW_HKEY, user_id, 0)

        balance = float(balance) if balance is not None else 0.0
        escrow = float(escrow) if escrow is not None else 0.0

        return balance - escrow

    @classmethod
    def increase_cash_balance(cls, user_id: str, amount: float) -> float:
        new_balance = REDIS_CLIENT.hincrbyfloat(CASH_BALANCE_HKEY, user_id, amount)
        if cls.queue is not None:
            cls.queue.put_nowait({"table": "Users", "data": {"cash_balance": amount}})
        return float(new_balance)

    @classmethod
    def decrease_cash_balance(cls, user_id: str, amount: float) -> float:
        new_balance = REDIS_CLIENT.hincrbyfloat(CASH_BALANCE_HKEY, user_id, -amount)
        if cls.queue is not None:
            cls.queue.put_nowait({"table": "Users", "data": {"cash_balance": -amount}})
        return float(new_balance)

    @classmethod
    def increase_cash_escrow(cls, user_id: str, amount: float) -> float:
        new_escrow = REDIS_CLIENT.hincrbyfloat(CASH_ESCROW_HKEY, user_id, amount)
        if cls.queue is not None:
            cls.queue.put_nowait({"table": "Users", "data": {"escrow_balance": amount}})
        return float(new_escrow)

    @classmethod
    def decrease_cash_escrow(cls, user_id: str, amount: float) -> float:
        new_escrow = REDIS_CLIENT.hincrbyfloat(CASH_ESCROW_HKEY, user_id, -amount)
        if cls.queue is not None:
            cls.queue.put_nowait(
                {"table": "Users", "data": {"escrow_balance": -amount}}
            )
        return float(new_escrow)

    @classmethod
    def get_asset_balance(cls, user_id: str, instrument_id: str) -> float:
        """Return available asset balance = balance - escrow."""
        balance_hkey = get_instrument_balance_hkey(instrument_id)
        escrow_hkey = get_instrument_escrows_hkey(instrument_id)

        balance = REDIS_CLIENT.hget(balance_hkey, user_id)
        escrow = REDIS_CLIENT.hget(escrow_hkey, user_id)

        if balance is None:
            REDIS_CLIENT.hset(balance_hkey, user_id, 0)
        if escrow is None:
            REDIS_CLIENT.hset(escrow_hkey, user_id, 0)

        balance = float(balance) if balance is not None else 0.0
        escrow = float(escrow) if escrow is not None else 0.0
        return balance - escrow

    @classmethod
    def increase_asset_balance(
        cls, user_id: str, instrument_id: str, amount: float
    ) -> float:
        hkey = get_instrument_balance_hkey(instrument_id)
        new_balance = REDIS_CLIENT.hincrbyfloat(hkey, user_id, amount)
        if cls.queue is not None:
            cls.queue.put_nowait(
                {
                    "table": "AssetBalances",
                    "data": {"instrument_id": instrument_id, "balance": amount},
                }
            )
        return float(new_balance)

    @classmethod
    def decrease_asset_balance(
        cls, user_id: str, instrument_id: str, amount: float
    ) -> float:
        hkey = get_instrument_balance_hkey(instrument_id)
        new_balance = REDIS_CLIENT.hincrbyfloat(hkey, user_id, -amount)
        if cls.queue is not None:
            cls.queue.put_nowait(
                {
                    "table": "AssetBalances",
                    "data": {"instrument_id": instrument_id, "balance": -amount},
                }
            )
        return float(new_balance)

    @classmethod
    def increase_asset_escrow(
        cls, user_id: str, instrument_id: str, amount: float
    ) -> float:
        hkey = get_instrument_escrows_hkey(instrument_id)
        new_escrow = REDIS_CLIENT.hincrbyfloat(hkey, user_id, amount)
        if cls.queue is not None:
            cls.queue.put_nowait(
                {
                    "table": "AssetBalances",
                    "data": {"instrument_id": instrument_id, "escrow_balance": amount},
                }
            )
        return float(new_escrow)

    @classmethod
    def decrease_asset_escrow(
        cls, user_id: str, instrument_id: str, amount: float
    ) -> float:
        hkey = get_instrument_escrows_hkey(instrument_id)
        new_escrow = REDIS_CLIENT.hincrbyfloat(hkey, user_id, -amount)
        if cls.queue is not None:
            cls.queue.put_nowait(
                {
                    "table": "AssetBalances",
                    "data": {"instrument_id": instrument_id, "escrow_balance": -amount},
                }
            )
        return float(new_escrow)

    @classmethod
    def settle_ask(
        cls, user_id: str, instrument_id: str, quantity: float, price: float
    ):
        with REDIS_CLIENT.pipeline() as pipe:
            pipe.hincrbyfloat(
                get_instrument_escrows_hkey(instrument_id), user_id, -quantity
            )
            pipe.hincrbyfloat(
                get_instrument_balance_hkey(instrument_id), user_id, -quantity
            )
            pipe.hincrbyfloat(CASH_BALANCE_HKEY, user_id, quantity * price)
            pipe.execute()

    @classmethod
    def settle_bid(
        cls, user_id: str, instrument_id: str, quantity: float, price: float
    ):
        total_value = quantity * price
        with REDIS_CLIENT.pipeline() as pipe:
            pipe.hincrbyfloat(CASH_ESCROW_HKEY, user_id, -total_value)
            pipe.hincrbyfloat(CASH_BALANCE_HKEY, user_id, -total_value)
            pipe.hincrbyfloat(
                get_instrument_balance_hkey(instrument_id), user_id, quantity
            )
            pipe.execute()
