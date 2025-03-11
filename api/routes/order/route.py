from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket
from fastapi.responses import JSONResponse
from sqlalchemy import select
from typing import Optional

from api.config import COOKIE_ALIAS
from config import REDIS_CLIENT
from db_models import Orders, Users
from enums import MarketType
from utils.db import get_db_session
from .controller import (
    enter_close_order,
    enter_modify_order,
    enter_new_order,
    get_futures_close_order_details,
    get_spot_close_order_details,
    validate_order_details,
)
from .client_manager import ClientManager
from .models import FuturesCloseOrder, ModifyOrder, OrderWrite, SpotCloseOrder
from ...middleware import JWT, verify_cookie, verify_cookie_http


order = APIRouter(prefix="/order", tags=["order"])
manager = ClientManager()


@order.websocket("/ws")
async def order_stream(ws: WebSocket) -> None:
    jwt = verify_cookie(ws.cookies)
    
    try:
        await manager.connect(ws, jwt['sub'])
        while True:
            await ws.receive()
    except RuntimeError:
        manager.disconnect(jwt["sub"])


@order.post("/")
async def create_order(body: OrderWrite, jwt: JWT = Depends(verify_cookie_http)):
    cmp: Optional[bytes] = await REDIS_CLIENT.get(f"{body.instrument}.price")
    if cmp is None:
        raise HTTPException(status_code=400, detail="Instrument isn't listed")

    current_market_price = float(cmp.decode())

    async with get_db_session() as sess:
        res = await sess.execute(
            select(Users.balance).where(Users.user_id == jwt["sub"])
        )
        balance = res.first()

    if balance is None:
        response = Response(status_code=403)
        response.delete_cookie(COOKIE_ALIAS)
        return response

    try:
        validate_order_details(current_market_price, body, balance[0])
        details = body.model_dump()
        details["price"] = current_market_price
        details["amount"] = round(details["quantity"] * current_market_price, 2)
        await enter_new_order(details, jwt["sub"], balance[0])
        return JSONResponse(status_code=201, content={"message": "Order placed"})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@order.put("/modify")
async def modify_order(body: ModifyOrder, jwt: JWT = Depends(verify_cookie_http)):
    async with get_db_session() as sess:
        res = await sess.execute(
            select(Orders).where(
                (Orders.order_id == body.order_id) & (Orders.user_id == jwt["sub"])
            )
        )
        order: Orders = res.scalar()

    if not order:
        raise HTTPException(status_code=400, detail="Order doesn't exist")

    try:
        await enter_modify_order(
            float((await REDIS_CLIENT.get(f"{order.instrument}.price")).decode()),
            order,
            body.limit_price,
            body.take_profit,
            body.stop_loss,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return Response(status_code=201)


@order.put("/close")
async def close_order(
    body: FuturesCloseOrder | SpotCloseOrder, jwt: JWT = Depends(verify_cookie_http)
):
    market_type: MarketType = (
        MarketType.FUTURES if isinstance(body, FuturesCloseOrder) else MarketType.SPOT
    )
    
    # price: Optional[bytes] = await REDIS_CLIENT.get(f"{details['instrument']}.price")
    # if price is None:
    #     raise HTTPException(status_code=400,)
    

    try:
        if market_type == MarketType.SPOT:
            func = get_spot_close_order_details(jwt["sub"], body)
        else:
            func = get_futures_close_order_details(jwt["sub"], body)
        details: dict = await func
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    details.update(
        {
            "price": float(
                (await REDIS_CLIENT.get(f"{details['instrument']}.price")).decode()
            ),
        }
    )

    await enter_close_order(
        market_type,
        details,
    )

    return Response(status_code=201)
