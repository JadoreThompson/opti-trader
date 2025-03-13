from typing import Optional
from pydantic import field_serializer
from ...base import CustomBase

class Profile(CustomBase):
    avatar: str
    username: str
    balance: float
    is_user: bool
    
    @field_serializer('balance')
    def balance_validator(self, value):
        return f"{round(value, 2):.2f}"
    

class UpdateProfile(CustomBase):
    email: Optional[str] = None
    username: Optional[str] = None
    
    
class AUM(CustomBase):
    value: float
    name: str
    
    @field_serializer('value')
    def value_serialiser(self, value: float) -> float:
        # return f"{round(value, 2):.2f}"
        return round(value, 2)