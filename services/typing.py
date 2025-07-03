from dataclasses import dataclass
from pydantic import BaseModel

class _Instrument(BaseModel):
    name: str
    price: float