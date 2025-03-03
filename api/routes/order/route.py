from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse


from config import REDIS_CLIENT
from .controller import enter_order, validate_order_details
from .models import OrderWrite
from ...middleware import verify_cookie

order = APIRouter(prefix="/order", tags=["order"])


@order.post("/")
async def create_order(body: OrderWrite, token: dict = Depends(verify_cookie)):
    p = await REDIS_CLIENT.get(f"{body.instrument}.price")

    if not p:
        raise HTTPException(status_code=400, detail="Invalid instrument")

    try:
        validate_order_details(float(p), body)
        await enter_order(body.model_dump(), token["sub"])
        return JSONResponse(status_code=201, content={"message": "Order placed"})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

