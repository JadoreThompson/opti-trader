from datetime import UTC, datetime
import sys


def get_exc_line():
    _, _, exc_tb = sys.exc_info()
    return exc_tb.tb_lineno


def get_datetime() -> datetime:
    return datetime.now(UTC)
