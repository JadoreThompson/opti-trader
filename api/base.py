from pydantic import BaseModel

class CustomBase(BaseModel):
    class Config:
        as_enum = True