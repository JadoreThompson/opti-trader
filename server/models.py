from typing import Generic, TypeVar
from pydantic import BaseModel, create_model

T = TypeVar("T")


class PaginationMeta(BaseModel):
    page: int
    size: int
    has_next: bool


class PaginatedResponse(PaginationMeta, Generic[T]):
    data: list[T]
    
hints  = {'name': str}
model = create_model('My Name', **hints)
print(model)

