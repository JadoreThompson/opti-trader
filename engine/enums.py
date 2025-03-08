from enum import Enum

class Tag(int, Enum):
    ENTRY = 0
    STOP_LOSS = 1
    TAKE_PROFIT = 2
    
class PositionStatus(int, Enum):
    """Represents whether it was manually closed"""
    UNTOUCHED = 0
    TOUCHED = 1