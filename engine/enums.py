from enum import Enum

class Tag(int, Enum):
    ENTRY = 0
    STOP_LOSS = 1
    TAKE_PROFIT = 2