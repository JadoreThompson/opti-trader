from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class PaginationMeta(BaseModel):
    page: int
    size: int
    has_next: bool


class PaginatedResponse(PaginationMeta, Generic[T]):
    data: list[T]
