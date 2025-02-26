from pydantic import BaseModel

class Base(BaseModel):
    class Config:
        as_enum = True