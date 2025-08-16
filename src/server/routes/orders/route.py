from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import PAGE_SIZE
from db_models import Orders
from enums import OrderStatus, Side
from server.middleware import convert_csv, verify_jwt
from server.typing import JWTPayload
from server.utils.db import depends_db_session
from .controller import (
    create_order as create_order_controller,
    create_oco_order as create_oco_order_controller,
    create_oto_order as create_oto_order_controller,
    create_otoco_order as create_otoco_order_controller,
)
from .models import (
    OCOOrderCreate,
    OTOCOOrderCreate,
    OTOOrderCreate,
    OrderCreate,
    OrderModify,
    OrderRead,
    PaginatedOrderResponse,
)
from .order_service import OrderService


route = APIRouter(prefix="/orders", tags=["orders"])


@route.post("/", status_code=202)
async def create_order(
    details: OrderCreate,
    jwt: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    """
    Accepts a new order. The order is placed on a queue for processing
    by the matching engine. The response is immediate and does not
    confirm the order has been filled.
    """
    try:
        return await OrderService.create(jwt.sub, details, db_sess)
    except IntegrityError:
        return JSONResponse(status_code=404, content={'error': "Invalid instrument."})


@route.post("/oco", status_code=202)
async def create_oco_order(
    details: OCOOrderCreate,
    jwt: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    try:
        return await OrderService.create(jwt.sub, details, db_sess)
    except IntegrityError:
        return JSONResponse(status_code=404, content={'error': "Invalid instrument."})


@route.post("/oto", status_code=202)
async def create_oto_order(
    details: OTOOrderCreate,
    jwt: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    try:
        return await OrderService.create(jwt.sub, details, db_sess)
    except IntegrityError:
        return JSONResponse(status_code=404, content={'error': "Invalid instrument."})


@route.post("/otoco", status_code=202)
async def create_otoco_order(
    details: OTOCOOrderCreate,
    jwt: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    try:
        return await OrderService.create(jwt.sub, details, db_sess)
    except IntegrityError:
        return JSONResponse(status_code=404, content={'error': "Invalid instrument."})


@route.get("/", response_model=PaginatedOrderResponse)
async def get_orders(
    page: int = Query(1, ge=1),
    instrument: list[str] = Query(default=[]),
    status: list[OrderStatus] = Query(default=[]),
    side: list[Side] = Query(default=[]),
    jwt: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    """
    Retrieves a paginated list of orders for the authenticated user,
    with optional filtering.
    """
    query = select(Orders).where(Orders.user_id == jwt.sub)

    if instrument:
        query = query.where(Orders.instrument_id.in_(instrument))
    if status:
        query = query.where(Orders.status.in_([s.value for s in status]))
    if side:
        query = query.where(Orders.side.in_([s.value for s in side]))

    offset = (page - 1) * PAGE_SIZE
    query = query.order_by(Orders.created_at.desc()).offset(offset).limit(PAGE_SIZE + 1)

    result = await db_sess.execute(query)
    orders = result.scalars().all()

    has_next = len(orders) > PAGE_SIZE

    return PaginatedOrderResponse(
        page=page,
        size=len(orders[:PAGE_SIZE]),
        has_next=has_next,
        data=[OrderRead(**vars(o)) for o in orders[:PAGE_SIZE]],
    )


@route.get("/{order_id}", response_model=OrderRead)
async def get_order(
    order_id: UUID,
    jwt: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    """Retrieves a single order by its ID."""
    order = await db_sess.get(Orders, order_id)
    if not order or order.user_id != jwt.sub:
        raise HTTPException(status_code=404, detail="Order not found")
    dumped = order.dump()
    dumped.pop("user_id")
    return OrderRead(**dumped)


@route.patch("/{order_id}", status_code=202, summary="Modify an active order")
async def modify_order(
    order_id: UUID,
    details: OrderModify,
    jwt: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    """Requests modification of an active order (e.g., changing the price)."""
    response = await modify_order(jwt.sub, order_id, details, db_sess)
    if not response:
        raise HTTPException(status_code=404, detail="Order not found or not active")
    return response


@route.delete("/", status_code=202, summary="Cancel all active orders for the user")
async def cancel_all_orders(
    jwt: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    """Sends requests to cancel all PENDING or PARTIALLY_FILLED orders."""
    await cancel_all_orders(jwt.sub, db_sess)


@route.delete("/{order_id}", status_code=202, summary="Cancel a specific order")
async def cancel_order(
    order_id: UUID,
    jwt: JWTPayload = Depends(verify_jwt),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    """Sends a request to cancel a specific order by its ID."""
    order_id = await cancel_order(jwt.sub, order_id, db_sess)
    if not order_id:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"order_id": str(order_id)}
