from datetime import timedelta
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import OrderEvents, Orders, Users
from server.middleware import verify_jwt
from server.models import PaginatedResponse
from server.typing import JWTPayload
from server.utils.db import depends_db_session
from utils.utils import get_datetime
from .controller import fetch_user_summary
from .models import (
    BalanceHistoryItem,
    OrderEventSummary,
    OrderQueryParams,
    OrderEventQueryParams,
    OrderResponse,
)


route = APIRouter(prefix="/user", tags=["user"])


@route.get("/orders", response_model=PaginatedResponse[OrderResponse])
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


@route.get("/orders/{order_id}", response_model=OrderResponse)
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


@route.get("/events", response_model=PaginatedResponse[OrderEventSummary])
async def get_events(
    params: Annotated[OrderEventQueryParams, Query()],
    jwt_payload: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    limit = 10
    offset = (params.page - 1) * 10
    stmt = select(OrderEvents).where(OrderEvents.user_id == jwt_payload.sub)

    if params.event_type is not None:
        stmt = stmt.where(OrderEvents.event_type.in_(params.event_type))
    if params.order_by:
        stmt = stmt.order_by(
            OrderEvents.created_at.desc()
            if params.order_by == "desc"
            else OrderEvents.created_at.asc()
        )

    res = await db_sess.execute(stmt.offset(offset).limit(limit + 1))
    events = res.scalars().all()

    return PaginatedResponse[OrderEventSummary](
        page=params.page,
        size=min(limit, len(events)),
        has_next=len(events) > limit,
        data=[
            OrderEventSummary(
                order_event_id=e.order_event_id,
                order_id=e.order_id,
                event_type=e.event_type,
                created_at=e.created_at,
            )
            for e in events
        ],
    )


@route.get("/summary")
async def get_current_user_summary(
    jwt_payload: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    return await fetch_user_summary(jwt_payload.sub, db_sess)


@route.get("/{user_id}/summary")
async def get_user_summary(
    user_id: str,
    _: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    return await fetch_user_summary(user_id, db_sess)


@route.get("/balance-history")
async def get_current_user_balance_history(
    jwt_payload: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    cur_datetime = get_datetime()
    res = await db_sess.execute(
        select(Users.balance).where(Users.user_id == jwt_payload.sub)
    )
    cur_balance = res.scalar()

    res = await db_sess.execute(
        select(Orders.created_at)
        .where(Orders.user_id == jwt_payload.sub)
        .order_by(Orders.created_at)
        .limit(1)
    )
    earliest_order_dt = res.scalar()

    res = await db_sess.execute(
        select(Orders.realised_pnl, Orders.created_at).where(Orders.user_id == jwt_payload.sub)
    )
    pnl_details = res.all()

    diff: timedelta = cur_datetime - earliest_order_dt
    n_parts = min(6, diff.days)
    if not n_parts:
        return []
    
    part_duration = diff // n_parts
    pnls: list[float] = []
    cur_order_dt = earliest_order_dt + part_duration

    for pnl, dt in pnl_details:     
        if dt <= cur_order_dt:
            if not pnls:
                pnls.append([cur_order_dt, pnl])
            else:
                pnls[-1][1] += pnl
        else:
            cur_order_dt += part_duration
            pnls.append([cur_order_dt, pnl])
            # print(cur_order_dt)   
    
    # results = [(cur_order_dt, cur_balance)]

    results = []
    for dt, pnl in pnls[::-1]:
        cur_balance -= pnl
        results.append((dt, cur_balance))


    return [BalanceHistoryItem(time=dt, balance=balance) for dt, balance in results]


@route.get("/{user_id}/balance-history")
async def get_user_balance_history(
    user_id: str,
    _: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
): ...
