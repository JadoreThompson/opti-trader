from pydantic import BaseModel

from server.models import PaginationMeta


class UserOverviewResponse(PaginationMeta):
    cash_balance: float
    data: dict[str, float]  # { BTC-USD: 100 }
