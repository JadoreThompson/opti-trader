import sys
from datetime import UTC, datetime


def get_exc_line():
    _, _, exc_tb = sys.exc_info()
    return exc_tb.tb_lineno


def get_datetime() -> datetime:
    return datetime.now(UTC)

def get_timestamp():
    return int(get_datetime().timestamp())