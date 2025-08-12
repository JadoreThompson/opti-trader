from pydantic import BaseModel

from server.models import PaginationMeta


class UserOverviewResponse(PaginationMeta):
    balance: float
    data: dict[str, float]  # { BTC-USD: 100 }
