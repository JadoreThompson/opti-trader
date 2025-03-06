from pydantic import field_serializer
from ...base import CustomBase

class Profile(CustomBase):
    avatar: str
    username: str
    balance: float
    
    @field_serializer('balance')
    def balance_validator(self, value):
        return f"{round(value, 2):.2f}"