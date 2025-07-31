from fastapi.responses import JSONResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from db_models import Orders, Users
from .models import UserSummary


async def fetch_user_summary(
    user_id: str, db_sess: AsyncSession
) -> UserSummary | JSONResponse:
    res = await db_sess.execute(select(Users.balance).where(Users.user_id == user_id))
    balance = res.scalar_one_or_none()
    if balance is None:
        return JSONResponse(status_code=404, content={"error": "User not found."})

    res = await db_sess.execute(
        select(func.coalesce(func.sum(Orders.realised_pnl), 0)).where(
            Orders.user_id == user_id
        )
    )
    realised_pnl = res.scalar()

    return UserSummary(balance=balance, pnl=realised_pnl)
