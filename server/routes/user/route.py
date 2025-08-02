from typing import Annotated
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import OrderEvents, Orders, Users
from enums import EventType, MarketType
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


@route.get("/balance-history", response_model=list[BalanceHistoryItem])
async def get_current_user_balance_history(
    market_type: MarketType = MarketType.FUTURES,
    jwt_payload: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    res = await db_sess.execute(
        select(Users.balance, Users.created_at).where(Users.user_id == jwt_payload.sub)
    )
    user_balance, user_created_at = res.one()

    res = await db_sess.execute(
        select(
            OrderEvents.created_at,
            OrderEvents.event_type,
            OrderEvents.quantity,
            OrderEvents.price,
            OrderEvents.balance,
            Orders.price.label("order_price"),
            Orders.quantity.label("order_quantity"),
        )
        .join(Orders, Orders.order_id == OrderEvents.order_id)
        .where(
            OrderEvents.user_id == jwt_payload.sub,
            Orders.market_type == market_type.value,
        )
        .order_by(OrderEvents.created_at)
    )
    events = res.all()

    default_item = [BalanceHistoryItem(time=user_created_at, balance=user_balance)]
    if not events:
        return default_item

    newest_date = events[-1].created_at
    oldest_date = events[0].created_at

    n_parts = 6
    part_duration = (newest_date - oldest_date) / n_parts

    i, l = 0, len(events)
    while i < l and events[i].event_type != EventType.ORDER_NEW:
        i += 1

    if i == l:
        return default_item

    event = events[i]
    starting_balance = event.balance + (event.quantity * event.price)
    result = [BalanceHistoryItem(time=event.created_at, balance=starting_balance)]
    max_date = event.created_at

    for e in events[i + 1 :]:
        if e.created_at <= max_date:
            result[-1].balance = e.balance
        else:
            max_date += part_duration
            result.append(BalanceHistoryItem(time=max_date, balance=e.balance))

    return result


@route.get("/{user_id}/balance-history")
async def get_user_balance_history(
    user_id: str,
    _: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
): ...
