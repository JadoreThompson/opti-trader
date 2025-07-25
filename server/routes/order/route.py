import asyncio
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select

from config import FUTURES_QUEUE_KEY, REDIS_CLIENT, SPOT_QUEUE_KEY
from db_models import Orders
from engine.typing import MODIFY_SENTINEL, Payload, PayloadTopic
from enums import MarketType, OrderStatus, OrderType, Side
from server.middleware import verify_jwt
from server.typing import JWTPayload
from server.utils.db import depends_db_session
from sqlalchemy.ext.asyncio import AsyncSession
from .controller import (
    handle_prepare_futures_order,
    handle_prepare_spot_ask_order,
    handle_prepare_spot_bid_order,
)
from .models import (
    MODIFY_ORDER_SENTINEL,
    BaseOrder,
    CancelOrder,
    CloseOrder,
    FuturesLimitOrder,
    FuturesMarketOrder,
    ModifyOrder,
    SpotLimitOCOOrder,
    SpotLimitOrder,
    SpotMarketOCOOrder,
    SpotMarketOrder,
)


route = APIRouter(prefix="/order", tags=["order"])


@route.post("/futures", status_code=201)
async def create_futures_order(
    body: BaseOrder,
    jwt_payload: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    dumped_body = body.model_dump()
    if body.order_type == OrderType.LIMIT:
        parsed_body = FuturesLimitOrder(**dumped_body)
    elif body.order_type == OrderType.MARKET:
        parsed_body = FuturesMarketOrder(**dumped_body)
    else:
        raise ValueError("Invlaid order type.")

    cur_price: float | None = await REDIS_CLIENT.get(parsed_body.instrument)
    if cur_price is None:
        return JSONResponse(
            status_code=400, content={"error": "Instrument doesn't exist."}
        )

    res = await handle_prepare_futures_order(
        parsed_body, jwt_payload.sub, cur_price, db_sess
    )

    if isinstance(res, JSONResponse):
        return res

    payload_data = {
        k: (str(v) if isinstance(v, (UUID, datetime)) else v) for k, v in res.items()
    }

    if body.order_type == OrderType.MARKET:
        payload_data["tmp_price"] = cur_price

    await REDIS_CLIENT.publish(
        FUTURES_QUEUE_KEY,
        Payload(
            topic=PayloadTopic.CREATE,
            data=payload_data,
        ).model_dump_json(),
    )

    return {"order_id": res["order_id"]}


@route.post("/spot", status_code=201)
async def create_spot_order(
    body: BaseOrder,
    jwt_payload: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    """Creates order, escrow record and sends to engine."""
    dumped_body = body.model_dump()
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
        res = await handle_prepare_spot_bid_order(
            parsed_body, jwt_payload.sub, cur_price, db_sess
        )
    else:
        res = await handle_prepare_spot_ask_order(parsed_body, jwt_payload.sub, db_sess)

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
    if body.limit_price is None:
        return JSONResponse(
            status_code=400, content={"error": "Limit price cannot be set to null."}
        )

    res = await db_sess.execute(
        select(Orders).where(
            Orders.order_id == order_id, Orders.user_id == jwt_payload.sub
        )
    )
    order = res.scalar_one_or_none()

    if order is None:
        return JSONResponse(status_code=400, content={"error": "Order doesn't exist."})

    if order.status == OrderStatus.CLOSED:
        return JSONResponse(
            status_code=400, content={"error": "Cannot modify closed order."}
        )

    await REDIS_CLIENT.publish(
        SPOT_QUEUE_KEY if order.market_type == MarketType.SPOT else FUTURES_QUEUE_KEY,
        Payload(
            topic=PayloadTopic.MODIFY,
            data={
                "order_id": order.order_id,
                "limit_price": (
                    body.limit_price
                    if body.limit_price != MODIFY_ORDER_SENTINEL
                    else MODIFY_SENTINEL
                ),
                "take_profit": (
                    body.take_profit
                    if body.take_profit != MODIFY_ORDER_SENTINEL
                    else MODIFY_SENTINEL
                ),
                "stop_loss": (
                    body.stop_loss
                    if body.stop_loss != MODIFY_ORDER_SENTINEL
                    else MODIFY_SENTINEL
                ),
            },
        ).model_dump_json(),
    )


@route.delete("/cancel/{order_id}", status_code=201)
async def cancel_order(
    order_id: str,
    body: CancelOrder,
    jwt_payload: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    res = await db_sess.execute(
        select(Orders).where(
            Orders.order_id == order_id, Orders.user_id == jwt_payload.sub
        )
    )
    order = res.scalar_one_or_none()
    if order is None:
        return JSONResponse(status_code=400, content={"error": "Order doesn't exist."})

    if body.quantity != "ALL" and order.standing_quantity < body.quantity:
        return JSONResponse(
            status_code=400, content={"error": "Insufficient standing quantity."}
        )

    await REDIS_CLIENT.publish(
        SPOT_QUEUE_KEY if order.market_type == MarketType.SPOT else FUTURES_QUEUE_KEY,
        Payload(
            topic=PayloadTopic.CANCEL,
            data={"order_id": order.order_id, "quantity": body.quantity},
        ).model_dump_json(),
    )


@route.delete("/close/{order_id}", status_code=201)
async def close_order(
    order_id: str,
    body: CloseOrder,
    jwt_payload: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    """Submits a close request for fully filled FUTURES order."""
    res = await db_sess.execute(
        select(Orders).where(
            Orders.user_id == jwt_payload.sub,
            Orders.order_id == order_id,
            Orders.market_type == MarketType.FUTURES,
        )
    )
    order = res.scalar_one_or_none()

    if order is None:
        return JSONResponse(status_code=400, content={"error": "Order doesn't exist."})
    if order.status not in (OrderStatus.FILLED, OrderStatus.PARTIALLY_CLOSED):
        return JSONResponse(status_code=400, content={"error": "Invalid order status."})

    if order.open_quantity == 0 or (
        body.quantity != "ALL" and body.quantity > order.open_quantity
    ):
        return JSONResponse(
            status_code=400, content={"error": "Insufficient open quantity."}
        )

    await REDIS_CLIENT.publish(
        (SPOT_QUEUE_KEY if order.market_type == MarketType.SPOT else FUTURES_QUEUE_KEY),
        Payload(
            topic=PayloadTopic.CLOSE,
            data={"order_id": order.order_id, "quantity": body.quantity},
        ).model_dump_json(),
    )

    return {"message": "All open orders are being closed."}
