from typing import Optional
from pydantic import Field, field_validator

from enums import MarketType, Side
from ...base import CustomBase


class LoginCredentials(CustomBase):
    email: str
    password: str
    
class RegisterCredentials(LoginCredentials):
    avatar: Optional[str] = Field("https://i.seadn.io/s/primary-drops/0xa06096e4640902c9713fcd91acf3d856ba4b0cc8/34399034:about:preview_media:b9117ca9-c56a-4c69-b3bf-5ec2d1ff3493.gif?auto=format&dpr=1&w=2048")
    username: str
    email: str
    password: str