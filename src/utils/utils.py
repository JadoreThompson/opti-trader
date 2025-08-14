from datetime import UTC, datetime


def get_datetime():
    return datetime.now(UTC)


def get_instrument_balance_hkey(instrument_id: str) -> str:
    return f"{instrument_id}.balances"


def get_instrument_escrows_hkey(instrument_id: str) -> str:
    return f"{instrument_id}.escrows"

def get_default_cash_balance() -> float: 
    return 10_000.00