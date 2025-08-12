from enum import Enum


class CommandType(Enum):
    NEW_ORDER = "NEW_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    MODIFY_ORDER = "MODIFY_ORDER"

class MatchOutcome(Enum):
    FAILURE = 0
    PARTIAL = 1
    SUCCESS = 2