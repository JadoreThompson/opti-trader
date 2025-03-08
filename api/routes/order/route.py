from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket
from fastapi.responses import JSONResponse
from redis import RedisCluster
from sqlalchemy import select

from config import REDIS_CLIENT
from db_models import Orders
from utils.db import get_db_session
from .controller import enter_modify_order, enter_new_order, validate_order_details
from .manager import ClientManager
from .models import ModifyOrder, OrderWrite
from ...middleware import JWT, verify_cookie, verify_cookie_http


order = APIRouter(prefix="/order", tags=["order"])
manager = ClientManager()


@order.websocket("/ws")
async def order_stream(ws: WebSocket) -> None:
    try:
        jwt = verify_cookie(ws.cookies)
        await manager.connect(ws)
        manager.append(ws, jwt["sub"])

        while True:
            await ws.receive()
    except RuntimeError:
        manager.disconnect(jwt["sub"])


@order.post("/")
async def create_order(body: OrderWrite, jwt: JWT = Depends(verify_cookie_http)):
    p = await REDIS_CLIENT.get(f"{body.instrument}.price")

    if not p:
        raise HTTPException(status_code=400, detail="Invalid instrument")

    try:
        validate_order_details(float(p.decode()), body)
        await enter_new_order(body.model_dump(), jwt["sub"])
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
        enter_modify_order(
            float((await REDIS_CLIENT.get(f"{order.instrument}.price")).decode()),
            order,
            body.limit_price,
            body.take_profit,
            body.stop_loss,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return Response(status_code=201)
