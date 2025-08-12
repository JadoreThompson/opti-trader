from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import PAGE_SIZE
from db_models import AssetBalances, Users
from server.middleware import verify_jwt
from server.typing import JWTPayload
from server.utils.db import depends_db_session
from .models import UserOverviewResponse


route = APIRouter(prefix="/user", tags=["user"])


@route.get("/", response_model=UserOverviewResponse)
async def get_user_overview(
    page: int = Query(1, ge=1),
    jwt_payload: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    user_balance = await db_sess.execute(
        select(Users.cash_balance).where(Users.user_id == jwt_payload.sub)
    )
    asset_balances = await db_sess.execute(
        select(AssetBalances.instrument_id, AssetBalances.balance)
        .where(AssetBalances.user_id == jwt_payload.sub)
        .offset((page - 1) * 10)
        .limit(PAGE_SIZE + 1)
    )

    return UserOverviewResponse(
        page=page,
        size=len(asset_balances),
        has_next=len(asset_balances) > PAGE_SIZE,
        balance=user_balance,
        data={instrument: balance for instrument, balance in asset_balances},
    )
