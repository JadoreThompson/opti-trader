from typing import Union
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select

from config import REDIS
from db_models import Users
from enums import OrderType, Side
from server.middleware import verify_jwt
from server.typing import JWTPayload
from server.utils.db import depends_db_session
from sqlalchemy.ext.asyncio import AsyncSession
from .models import BaseOrder, SpotLimitOrder, SpotMarketOrder


route = APIRouter(prefix="/order", tags=["order"])


@route.post("/spot")
async def create_order(
    body: BaseOrder,
    jwt_payload: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    if body.order_type == OrderType.LIMIT:
        parsed_body = SpotLimitOrder(**body.model_dump(), **body.model_extra)
    elif body.order_type == OrderType.MARKET:
        parsed_body = SpotMarketOrder(**body.model_dump(), **body.model_extra)
    else:
        raise ValueError("Invlaid order type.")

    prev_price = await REDIS.get(parsed_body.instrument)
    if prev_price is None:
        return JSONResponse(
            status_code=400, content={"error": "Instrument doesn't exist."}
        )

    if parsed_body.side == Side.BID:
        res = await db_sess.execute(
            select(Users.balance).where(Users.user_id == jwt_payload.sub)
        )
        balance = res.scalar()

        if body.quantity * prev_price > balance:
            return JSONResponse(
                status_code=400, content={"error": "Insufficient balance."}
            )
    else:
        # res = await db_sess.execute(
        #     select(Users.balance).where(Users.user_id == jwt_payload.sub)
        # )
        # ...
        ...
    balance = res.scalar()
    if parsed_body.quantity * prev_price > balance:
        return JSONResponse(status_code=400, content={"error": "Insufficient balance."})
