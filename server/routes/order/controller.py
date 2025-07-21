from fastapi.responses import JSONResponse
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Union

from db_models import Escrows, OrderEvents, Orders, Users
from engine.typing import EventType
from enums import MarketType, OrderType
from .models import SpotLimitOCOOrder, SpotLimitOrder, SpotMarketOCOOrder, SpotMarketOrder


async def handle_place_spot_bid_order(
    order: Union[
        SpotLimitOCOOrder, SpotLimitOrder, SpotMarketOCOOrder, SpotMarketOrder
    ],
    user_id: str,
    current_price: float,
    db_sess: AsyncSession,
) -> JSONResponse | dict:
    """
    Validates balance, creates escrow and order record.
    Returns a 400 JSON error if balance is insufficient.

    Args:
        order (Union[SpotMarketOrder, SpotLimitOrder]): Spot order details.
        user_id (int): Identifier of the user placing the order.
        current_price (float): Current market price used to value the order.
        db_sess (AsynsSession): Active async database session.

    Returns:
        JSONResponse | dict:
            JSONResponse: Insufficient balance.
            dict: Dictionary representation of an Orders object.
    """
    res = await db_sess.execute(select(Users.balance).where(Users.user_id == user_id))
    balance = res.scalar()

    order_value = (
        order.quantity * current_price
        if order.order_type in (OrderType.MARKET, OrderType.MARKET_OCO)
        else order.quantity * order.limit_price
    )

    if order_value > balance:
        return JSONResponse(status_code=400, content={"error": "Insufficient balance."})

    res = await db_sess.execute(
        update(Users)
        .values(
            balance=select(Users.balance)
            .where(Users.user_id == user_id)
            .scalar_subquery()
            - order_value
        )
        .returning(Users.balance)
    )
    user_balance = res.scalar()

    res = await db_sess.execute(
        insert(Orders)
        .values(
            **order.model_dump(),
            user_id=user_id,
            market_type=MarketType.SPOT.value,
            standing_quantity=order.quantity
        )
        .returning(Orders)
    )
    db_order = res.scalar()

    res = await db_sess.execute(
        select(OrderEvents.asset_balance)
        .where(
            OrderEvents.user_id == user_id,
            OrderEvents.order_id.in_(
                select(Orders.order_id)
                .where(
                    Orders.user_id == user_id,
                    Orders.instrument == order.instrument,
                )
                .scalar_subquery()
            ),
        )
        .order_by(OrderEvents.created_at.desc())
        .limit(1)
    )
    cur_asset_balance = res.scalar_one_or_none() or 0

    await db_sess.execute(
        insert(OrderEvents).values(
            user_id=user_id,
            order_id=db_order.order_id,
            event_type=EventType.BID_SUBMITTED,
            asset_balance=cur_asset_balance,
            balance=user_balance,
        )
    )

    await db_sess.execute(
        insert(Escrows).values(
            user_id=user_id, order_id=db_order.order_id, balance=order_value
        )
    )

    await db_sess.commit()
    return db_order.dump()


async def handle_place_spot_ask_order(
    order: Union[SpotMarketOrder, SpotLimitOrder],
    user_id: str,
    db_sess: AsyncSession,
) -> JSONResponse | dict:
    """
    Places and validates a spot ask order.

    Args:
        order (Union[SpotMarketOrder, SpotLimitOrder]): Spot order details.
        user_id (str): User id being used to place order.
        db_sess (AsyncSession): Active async database session.

    Returns:
        JSONResponse | dict:
            JSONResponse: Insufficient balance.
            dict: Dictionary representation of an Orders object.
    """
    res = await db_sess.execute(
        select(OrderEvents.asset_balance)
        .where(
            OrderEvents.user_id == user_id,
            OrderEvents.order_id.in_(
                select(Orders.order_id)
                .where(Orders.user_id == user_id, Orders.instrument == order.instrument)
                .scalar_subquery()
            ),
        )
        .order_by(OrderEvents.created_at.desc())
        .limit(1)
    )
    asset_balance = res.scalar_one_or_none()

    if asset_balance is None or order.quantity > asset_balance:
        return JSONResponse(
            status_code=400, content={"error": "Insufficient asset balance."}
        )

    # Barring off quantity
    res = await db_sess.execute(
        insert(Orders)
        .values(
            user_id=user_id,
            market_type=MarketType.SPOT,
            standing_quantity=order.quantity,
            **order.model_dump()
        )
        .returning(Orders)
    )
    db_order = res.scalar()

    await db_sess.execute(
        insert(OrderEvents).values(
            user_id=user_id,
            order_id=db_order.order_id,
            event_type=EventType.ASK_SUBMITTED,
            asset_balance=asset_balance - order.quantity,
            balance=select(Users.balance).where(Users.user_id == user_id),
        )
    )

    await db_sess.commit()
    return db_order.dump()
