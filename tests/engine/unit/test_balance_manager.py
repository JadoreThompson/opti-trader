import pytest
from unittest.mock import MagicMock

from src.config import REDIS_CLIENT, CASH_BALANCE_HKEY, CASH_ESCROW_HKEY
from src.engine.balance_manager import BalanceManager
from src.utils.utils import get_instrument_balance_hkey, get_instrument_escrows_hkey


USER_ID = "test_user_1"
INSTRUMENT_ID = "BTC-USD"


@pytest.fixture(autouse=True)
def clean_redis_for_balance_manager():
    """Fixture to clean up Redis keys used by BalanceManager before and after each test."""
    keys_to_delete = [
        CASH_BALANCE_HKEY,
        CASH_ESCROW_HKEY,
        get_instrument_balance_hkey(INSTRUMENT_ID),
        get_instrument_escrows_hkey(INSTRUMENT_ID),
    ]
    REDIS_CLIENT.delete(*keys_to_delete)
    yield
    REDIS_CLIENT.delete(*keys_to_delete)


def test_get_user_balance_for_new_user():
    """
    Tests that getting the balance for a user who does not exist in Redis returns 0
    and that their initial balance and escrow are set to 0.
    """
    assert BalanceManager.get_user_balance("new_user") == 0.0
    assert float(REDIS_CLIENT.hget(CASH_BALANCE_HKEY, "new_user")) == 0.0
    assert float(REDIS_CLIENT.hget(CASH_ESCROW_HKEY, "new_user")) == 0.0


def test_increase_and_decrease_cash_balance():
    """
    Tests that a user's cash balance can be correctly increased and decreased.
    """
    assert BalanceManager.get_user_balance(USER_ID) == 0.0

    BalanceManager.increase_cash_balance(USER_ID, 1000.0)
    assert BalanceManager.get_user_balance(USER_ID) == 1000.0
    assert float(REDIS_CLIENT.hget(CASH_BALANCE_HKEY, USER_ID)) == 1000.0

    BalanceManager.decrease_cash_balance(USER_ID, 400.0)
    assert BalanceManager.get_user_balance(USER_ID) == 600.0
    assert float(REDIS_CLIENT.hget(CASH_BALANCE_HKEY, USER_ID)) == 600.0


def test_increase_and_decrease_cash_escrow():
    """
    Tests that cash escrow operations correctly affect the available user balance.
    """
    BalanceManager.increase_cash_balance(USER_ID, 1000.0)

    BalanceManager.increase_cash_escrow(USER_ID, 300.0)
    assert float(REDIS_CLIENT.hget(CASH_ESCROW_HKEY, USER_ID)) == 300.0
    assert BalanceManager.get_user_balance(USER_ID) == 700.0  # 1000 total - 300 escrow

    BalanceManager.decrease_cash_escrow(USER_ID, 100.0)
    assert float(REDIS_CLIENT.hget(CASH_ESCROW_HKEY, USER_ID)) == 200.0
    assert BalanceManager.get_user_balance(USER_ID) == 800.0  # 1000 total - 200 escrow


def test_get_asset_balance_for_new_user():
    """
    Tests that getting an asset balance for a user with no holdings returns 0
    and initializes their asset balance and escrow to 0.
    """
    assert BalanceManager.get_asset_balance(USER_ID, INSTRUMENT_ID) == 0.0
    balance_hkey = get_instrument_balance_hkey(INSTRUMENT_ID)
    escrow_hkey = get_instrument_escrows_hkey(INSTRUMENT_ID)
    assert float(REDIS_CLIENT.hget(balance_hkey, USER_ID)) == 0.0
    assert float(REDIS_CLIENT.hget(escrow_hkey, USER_ID)) == 0.0


def test_increase_and_decrease_asset_balance():
    """
    Tests that a user's asset balance can be correctly increased and decreased.
    """
    BalanceManager.increase_asset_balance(USER_ID, INSTRUMENT_ID, 10.5)
    assert BalanceManager.get_asset_balance(USER_ID, INSTRUMENT_ID) == 10.5

    BalanceManager.decrease_asset_balance(USER_ID, INSTRUMENT_ID, 2.5)
    assert BalanceManager.get_asset_balance(USER_ID, INSTRUMENT_ID) == 8.0


def test_increase_and_decrease_asset_escrow():
    """
    Tests that asset escrow operations correctly affect the available asset balance.
    """
    BalanceManager.increase_asset_balance(USER_ID, INSTRUMENT_ID, 10.0)

    BalanceManager.increase_asset_escrow(USER_ID, INSTRUMENT_ID, 4.0)
    assert (
        BalanceManager.get_asset_balance(USER_ID, INSTRUMENT_ID) == 6.0
    )  # 10 total - 4 escrow

    BalanceManager.decrease_asset_escrow(USER_ID, INSTRUMENT_ID, 1.5)
    assert (
        BalanceManager.get_asset_balance(USER_ID, INSTRUMENT_ID) == 7.5
    )  # 10 total - 2.5 escrow


def test_settle_bid_operation():
    """
    Tests the pipeline of operations for settling a buy (BID) trade, ensuring
    cash and asset balances are correctly updated.
    """
    BalanceManager.increase_cash_balance(USER_ID, 1000.0)
    BalanceManager.increase_cash_escrow(USER_ID, 500.0)
    BalanceManager.increase_asset_balance(USER_ID, INSTRUMENT_ID, 5.0)

    BalanceManager.settle_bid(USER_ID, INSTRUMENT_ID, quantity=2.0, price=250.0)

    assert float(REDIS_CLIENT.hget(CASH_BALANCE_HKEY, USER_ID)) == 500.0
    assert float(REDIS_CLIENT.hget(CASH_ESCROW_HKEY, USER_ID)) == 0.0
    assert (
        float(REDIS_CLIENT.hget(get_instrument_balance_hkey(INSTRUMENT_ID), USER_ID))
        == 7.0
    )


def test_settle_ask_operation():
    """
    Tests the pipeline of operations for settling a sell (ASK) trade, ensuring
    cash and asset balances are correctly updated.
    """
    BalanceManager.increase_cash_balance(USER_ID, 1000.0)
    BalanceManager.increase_asset_balance(USER_ID, INSTRUMENT_ID, 10.0)
    BalanceManager.increase_asset_escrow(USER_ID, INSTRUMENT_ID, 4.0)

    BalanceManager.settle_ask(USER_ID, INSTRUMENT_ID, quantity=4.0, price=300.0)

    assert float(REDIS_CLIENT.hget(CASH_BALANCE_HKEY, USER_ID)) == 2200.0
    assert REDIS_CLIENT.hget(CASH_ESCROW_HKEY, USER_ID) is None
    assert (
        float(REDIS_CLIENT.hget(get_instrument_balance_hkey(INSTRUMENT_ID), USER_ID))
        == 6.0
    )
    assert (
        float(REDIS_CLIENT.hget(get_instrument_escrows_hkey(INSTRUMENT_ID), USER_ID))
        == 0.0
    )
