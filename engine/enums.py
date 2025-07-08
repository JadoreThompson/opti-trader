from enum import Enum


class Tag(int, Enum):
    ENTRY = 0
    STOP_LOSS = 1
    TAKE_PROFIT = 2
    DUMMY = 3


class PositionStatus(int, Enum):
    """Represents whether it was manually closed"""

    UNTOUCHED = 0
    TOUCHED = 1


class MatchOutcome(int, Enum):
    FAILURE = 0  # No price avaialable
    PARTIAL = 1  # Partial match, some orders matched
    SUCCESS = 2  # Full match, all orders matched


class EnginePayloadCategory(int, Enum):
    """All categories of payloads to be sent to the engine"""

    NEW = 0
    MODIFY = 1
    CLOSE = 2
    CANCEL = 4
    APPEND = 5  # Append Orderbook
