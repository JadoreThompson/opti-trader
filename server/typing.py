from dataclasses import dataclass
from datetime import datetime


@dataclass
class JWTPayload:
    sub: str  # user id
    exp: datetime
