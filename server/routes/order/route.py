import asyncio
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select

from config import REDIS_CLIENT, SPOT_QUEUE_KEY
from db_models import Orders
from engine.typing import MODIFY_DEFAULT, Payload, PayloadTopic
from enums import MarketType, OrderStatus, OrderType, Side
from server.middleware import verify_jwt
from server.typing import JWTPayload
from server.utils.db import depends_db_session
from sqlalchemy.ext.asyncio import AsyncSession
from .controller import (
    handle_place_spot_ask_order,
    handle_place_spot_bid_order,
)
from .models import (
    BaseOrder,
    ModifyOrder,
    SpotLimitOCOOrder,
    SpotLimitOrder,
    SpotMarketOCOOrder,
    SpotMarketOrder,
)


route = APIRouter(prefix="/order", tags=["order"])


@route.post("/spot", status_code=201)
async def create_order(
    body: BaseOrder,
    jwt_payload: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    """Creates order, escrow record and sends to engine."""
    dumped_body = body.model_dump()
    # if body.order_type == OrderType.LIMIT:
    #     parsed_body = SpotLimitOrder(**dumped_body)
    # elif body.order_type == OrderType.MARKET:
    #     parsed_body = SpotMarketOrder(**dumped_body)
    # else:
    #     raise ValueError("Invlaid order type.")

    if body.order_type == OrderType.LIMIT:
        parsed_body = SpotLimitOrder(**dumped_body)
    elif body.order_type == OrderType.LIMIT_OCO:
        parsed_body = SpotLimitOCOOrder(**dumped_body)
    elif body.order_type == OrderType.MARKET:
        parsed_body = SpotMarketOrder(**dumped_body)
    elif body.order_type == OrderType.MARKET_OCO:
        parsed_body = SpotMarketOCOOrder(**dumped_body)
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
    else:
        res = await handle_place_spot_ask_order(body, jwt_payload.sub, db_sess)

    if isinstance(res, JSONResponse):
        return res

    await REDIS_CLIENT.publish(
        SPOT_QUEUE_KEY,
        Payload(
            topic=PayloadTopic.CREATE,
            data={
                k: (str(v) if isinstance(v, (UUID, datetime)) else v)
                for k, v in res.items()
            },
        ).model_dump_json(),
    )

    return {"order_id": res["order_id"]}


@route.patch("/modify/{order_id}", status_code=201)
async def modify_order(
    order_id: str,
    body: ModifyOrder,
    jwt_payload: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    res = await db_sess.execute(
        select(
            Orders.market_type, Orders.status, Orders.order_type, Orders.instrument
        ).where(Orders.order_id == order_id, Orders.user_id == jwt_payload.sub)
    )
    data = res.first()

    if not data:
        return JSONResponse(status_code=400, content={"error": "Order doesn't exist."})

    market_type, order_status, order_type, instrument = data

    cur_price: float | None = await REDIS_CLIENT.get(instrument)
    if cur_price is None:
        return JSONResponse(
            status_code=400, content={"error": "Instrument doesn't exist."}
        )

    if market_type == MarketType.FUTURES:
        if order_status not in (OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED):
            return JSONResponse(
                status_code=400,
                content={"error": f"Cannot modify order with status {order_status}."},
            )

    elif market_type == MarketType.SPOT:
        if body.limit_price != MODIFY_DEFAULT and order_type not in (
            OrderType.LIMIT,
            OrderType.LIMIT_OCO,
        ):
            return JSONResponse(
                status_code=400,
                content={
                    "error": f"Cannot limit price for order type {order_type}. Must be a limit order."
                },
            )

        if (
            body.take_profit != MODIFY_DEFAULT
            or body.stop_loss != MODIFY_DEFAULT
            and order_type not in (OrderType.LIMIT_OCO, OrderType.MARKET_OCO)
        ):
            return JSONResponse(
                status_code=400,
                content={
                    "error": f"Cannot take profit or stop loss price for order type {order_type}. Must be an OCO order."
                },
            )
