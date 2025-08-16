from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import AssetBalances, Events, Trades, Users
from server.middleware import verify_jwt
from server.typing import JWTPayload
from server.utils import depends_db_session
from .controller import get_portfolio_history
from .models import (
    UserEvents,
    HistoryInterval,
    PortfolioHistory,
    UserOverviewResponse,
)


route = APIRouter(prefix="/user", tags=["user"])


@route.get("/")
async def get_user_overview(
    page: int = Query(1, ge=1),
    jwt: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    res = await db_sess.execute(
        select(Users.cash_balance - Users.escrow_balance).where(
            Users.user_id == jwt.sub
        )
    )
    cash_balance = res.scalar()

    balances_subq = (
        select(AssetBalances.instrument_id, AssetBalances.balance)
        .where(AssetBalances.user_id == jwt.sub)
        .subquery()
    )

    latest_trade_subq = (
        select(Trades.instrument_id, Trades.price)
        .where(Trades.user_id == jwt.sub)
        .order_by(Trades.executed_at.desc())
        .subquery()
    )

    stmt = (
        select(
            balances_subq.c.instrument_id,
            balances_subq.c.balance * latest_trade_subq.c.price,
        )
        .join(
            latest_trade_subq,
            balances_subq.c.instrument_id == latest_trade_subq.c.instrument_id,
        )
        .distinct(balances_subq.c.instrument_id)
    )

    res = await db_sess.execute(stmt)
    rows = res.all()

    portfolio_balance = 0.0
    data = {}

    for instrument, balance in rows:
        portfolio_balance += balance
        data[instrument] = balance

    return UserOverviewResponse(
        cash_balance=cash_balance,
        portfolio_balance=portfolio_balance,
        data=data,
    )


@route.get("/history", response_model=list[PortfolioHistory])
async def get_user_portfolio_history(
    interval: HistoryInterval,
    jwt: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    history = await get_portfolio_history(interval, jwt.sub, 6, db_sess)
    return history


@route.get("/events", response_model=list[UserEvents])
async def get_user_events(
    size: int = Query(10, ge=1),
    jwt: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    size = min(20, size)
    res = await db_sess.execute(
        select(Events.event_type, Events.related_id).where(Events.user_id == jwt.sub).limit(size)
    )
    events = res.all()
    return [UserEvents(event_type=etype, order_id=str(oid)) for etype, oid in events]
