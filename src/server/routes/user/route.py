from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import PAGE_SIZE
from db_models import AssetBalances, Users
from server.middleware import verify_jwt
from server.typing import JWTPayload
from server.utils.db import depends_db_session
from .controller import get_portfolio_history
from .models import HistoryInterval, PortfolioHistory, UserOverviewResponse


route = APIRouter(prefix="/user", tags=["user"])


@route.get("/", response_model=UserOverviewResponse)
async def get_user_overview(
    page: int = Query(1, ge=1),
    jwt_payload: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    res = await db_sess.execute(
        select(Users.cash_balance).where(Users.user_id == jwt_payload.sub)
    )
    user_balance = res.scalar()
    res = await db_sess.execute(
        select(AssetBalances.instrument_id, AssetBalances.balance)
        .where(AssetBalances.user_id == jwt_payload.sub)
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE + 1)
    )
    asset_balances = res.all()

    return UserOverviewResponse(
        page=page,
        size=len(asset_balances),
        has_next=len(asset_balances) > PAGE_SIZE,
        cash_balance=user_balance,
        data={instrument: balance for instrument, balance in asset_balances},
    )


@route.get("/history", response_model=list[PortfolioHistory])
async def get_user_portfolio_history(
    interval: HistoryInterval,
    jwt: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    history = await get_portfolio_history(interval, jwt.sub, 6, db_sess)
    return history
