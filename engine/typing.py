from collections import namedtuple
from enum import Enum
from typing import TypedDict


MatchResult = namedtuple(
    "MatchResult",
    (
        "outcome",
        "price",
    ),
)


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


class EnginePayload(TypedDict):
    """Payload Schema for submitting requests to the engine"""

    category: EnginePayloadCategory
    content: dict
