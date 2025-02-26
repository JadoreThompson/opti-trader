from fastapi import APIRouter, Depends

from .controller import enter_order
from .models import OrderWrite
from ...middleware import verify_token

order = APIRouter(prefix="/order", tags=["order"])

@order.post("/")
async def create_order(body: OrderWrite, token: dict = Depends(verify_token)):
    await enter_order(body.model_dump(), token['sub'])
    return body