from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import insert, select, update

from config import REDIS_CLIENT
from db_models import Escrows, OrderEvents, Orders, Users
from enums import MarketType, OrderType, Side
from server.middleware import verify_jwt
from server.typing import JWTPayload
from server.utils.db import depends_db_session
from sqlalchemy.ext.asyncio import AsyncSession
from .controller import handle_place_spot_ask_order, handle_place_spot_bid_order
from .models import BaseOrder, SpotLimitOrder, SpotMarketOrder


route = APIRouter(prefix="/order", tags=["order"])


@route.post("/spot", status_code=201)
async def create_order(
    body: BaseOrder,
    jwt_payload: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    """Creates order, escrow record and sends to engine."""
    dumped_body = body.model_dump()
    if body.order_type == OrderType.LIMIT:
        parsed_body = SpotLimitOrder(**dumped_body)
    elif body.order_type == OrderType.MARKET:
        parsed_body = SpotMarketOrder(**dumped_body)
    else:
        raise ValueError("Invlaid order type.")

    cur_price: float | None = await REDIS_CLIENT.get(parsed_body.instrument)
    if cur_price is None:
        return JSONResponse(
            status_code=400, content={"error": "Instrument doesn't exist."}
        )

    if parsed_body.side == Side.BID:
        res = await handle_place_spot_bid_order(
            body, jwt_payload.sub, cur_price, db_sess
        )
        if isinstance(res, str):
            return {"order_id": res}
        return res
    else:
        res = await handle_place_spot_ask_order(
            body, jwt_payload.sub, db_sess
        )
        if isinstance(res, str):
            return {"order_id": res}
        return res
