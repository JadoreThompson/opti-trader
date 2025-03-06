import json
from fastapi import APIRouter, Depends, HTTPException, WebSocket
from fastapi.responses import JSONResponse

from config import REDIS_CLIENT
from .controller import enter_order, validate_order_details
from .manager import ClientManager
from .models import OrderWrite, SocketPayload
from ...middleware import JWT, verify_cookie, verify_cookie_http

order = APIRouter(prefix="/order", tags=["order"])
manager = ClientManager()


@order.websocket("/ws")
async def order_stream(ws: WebSocket):
    try:
        jwt = verify_cookie(ws.cookies)
        await manager.connect(ws)
        m = await ws.receive_text()

        payload = SocketPayload(**json.loads(m))
        await manager.append(ws, jwt["sub"], payload.content)

        while True:
            await ws.receive()
    except RuntimeError:
        await manager.disconnect(jwt["sub"])


@order.post("/")
async def create_order(body: OrderWrite, jwt: JWT = Depends(verify_cookie_http)):
    p = await REDIS_CLIENT.get(f"{body.instrument}.price")

    if not p:
        raise HTTPException(status_code=400, detail="Invalid instrument")

    try:
        # print(body)
        validate_order_details(float(p.decode()), body)
        await enter_order(body.model_dump(), jwt["sub"])
        return JSONResponse(status_code=201, content={"message": "Order placed"})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
