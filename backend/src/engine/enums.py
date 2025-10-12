from enum import Enum


class CommandType(Enum):
    NEW_ORDER = "NEW_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    MODIFY_ORDER = "MODIFY_ORDER"
    NEW_INSTRUMENT = "NEW_INSTRUMENT"


class MatchOutcome(Enum):
    FAILURE = 0  # 0 quantity matched
    PARTIAL = 1  # > 0 quantity matched
    SUCCESS = 2  # full quantity matched
    UNAUTHORISED = 3  # didn't pass risk checks.
