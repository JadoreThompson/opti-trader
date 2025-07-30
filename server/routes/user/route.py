from typing import Annotated
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import Orders
from server.middleware import verify_jwt
from server.models import PaginatedResponse
from server.typing import JWTPayload
from server.utils.db import depends_db_session
from .models import OrderQueryParams, OrderResponse


route = APIRouter(prefix="/user", tags=["user"])


@route.get("/orders")
async def get_orders(
    params: Annotated[OrderQueryParams, Query()],
    jwt_payload: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    limit = 10
    offset = (params.page - 1) * limit

    stmt = select(Orders).where(Orders.user_id == jwt_payload.sub)

    if params.market_type:
        stmt = stmt.where(Orders.market_type.in_(params.market_type))
    if params.status:
        stmt = stmt.where(Orders.status.in_(params.status))
    if params.order_type:
        stmt = stmt.where(Orders.order_type.in_(params.order_type))

    result = await db_sess.execute(
        stmt.offset(offset).limit(limit + 1).order_by(Orders.created_at.desc())
    )
    orders = result.scalars().all()

    return PaginatedResponse[OrderResponse](
        page=params.page,
        size=min(limit, len(orders)),
        has_next=len(orders) > limit,
        data=[OrderResponse(**o.dump()) for o in orders[:limit]],
    )


@route.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    jwt_payload: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    order = await db_sess.execute(
        select(Orders).where(
            Orders.order_id == order_id, Orders.user_id == jwt_payload.sub
        )
    )
    order = order.scalar_one_or_none()
    if order is None:
        return JSONResponse(status_code=400, content={"error": "Order doesn't exist."})

    return OrderResponse(**order.dump())
