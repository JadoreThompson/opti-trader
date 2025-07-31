from fastapi.responses import JSONResponse
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Union

from db_models import Escrows, OrderEvents, Orders, Users
from engine.typing import EventType
from enums import MarketType, OrderStatus, OrderType, Side
from .models import (
    MODIFY_ORDER_SENTINEL,
    FuturesLimitOrder,
    FuturesMarketOrder,
    SpotLimitOCOOrder,
    SpotLimitOrder,
    SpotMarketOCOOrder,
    SpotMarketOrder,
)


async def handle_prepare_spot_bid_order(
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
            standing_quantity=order.quantity,
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


async def handle_prepare_spot_ask_order(
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
            **order.model_dump(),
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


async def handle_prepare_futures_order(
    order: Union[FuturesLimitOrder, FuturesMarketOrder],
    user_id: str,
    current_price: float,
    db_sess: AsyncSession,
) -> JSONResponse | tuple[dict, float]:
    """
    Validates futures order and creates the order record.

    Args:
        order (Union[FuturesLimitOrder, FuturesMarketOrder]): Futures order details.
        user_id (str): Identifier of the user placing the order.
        current_price (float): Current market price used to value the order.
        db_sess (AsyncSession): Active async database session.

    Returns:
        tuple[dict, float]:
            - dict: Dictionary representation of an Orders record.
            - float: New balance after transaction.
    """
    res = await db_sess.execute(select(Users.balance).where(Users.user_id == user_id))
    balance = res.scalar()

    order_value = (
        order.quantity * current_price
        if order.order_type == OrderType.MARKET
        else order.quantity * order.limit_price
    )

    if order_value > balance:
        return JSONResponse(status_code=400, content={"error": "Insufficient balance."})

    tmp_stop_loss = order.stop_loss or (
        float("-inf") if order.side == Side.BID else float("inf")
    )
    tmp_take_profit = order.take_profit or (
        float("inf") if order.side == Side.BID else float("-inf")
    )

    if (
        order.side == Side.BID and not (tmp_stop_loss < current_price < tmp_take_profit)
    ) or (
        order.side == Side.ASK and not (tmp_stop_loss > current_price > tmp_take_profit)
    ):
        return JSONResponse(status_code=400, content={"error": "Invalid TP/SL"})

    if order.order_type == OrderType.LIMIT:
        if (
            order.side == Side.BID
            and not (
                tmp_stop_loss < order.limit_price <= current_price < tmp_take_profit
            )
        ) or (
            order.side == Side.ASK
            and not (
                tmp_stop_loss > order.limit_price >= current_price > tmp_take_profit
            )
        ):
            return JSONResponse(status_code=400, content={"error": "Invalid TP/SL"})

    res = await db_sess.execute(
        insert(Orders)
        .values(
            **order.model_dump(),
            user_id=user_id,
            market_type=MarketType.FUTURES.value,
            standing_quantity=order.quantity,
            price=current_price,
        )
        .returning(Orders)
    )
    db_order = res.scalar_one()

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

    await db_sess.execute(
        insert(OrderEvents).values(
            user_id=user_id,
            order_id=str(db_order.order_id),
            event_type=(
                EventType.ASK_SUBMITTED
                if order.side == Side.ASK
                else EventType.BID_SUBMITTED
            ),
            asset_balance=0,
            balance=user_balance,
        )
    )

    await db_sess.execute(
        insert(Escrows).values(
            user_id=user_id, order_id=db_order.order_id, balance=order_value
        )
    )

    await db_sess.commit()
    return db_order.dump(), user_balance


def validate_modify_order(
    cur_price: float,
    order_type: OrderType,
    order_status: OrderStatus,
    side: Side,
    limit_price: float | None = None,
    new_limit_price: float = MODIFY_ORDER_SENTINEL,
    stop_loss: float | None = None,
    new_stop_loss: float = MODIFY_ORDER_SENTINEL,
    take_profit: float | None = None,
    new_take_profit: float = MODIFY_ORDER_SENTINEL,
) -> bool:
    """
    Validates whether a requested order modification is logically and structurally valid,

    Args:
        cur_price (float): The current market price of the asset.
        order_type (OrderType): The type of the order.
        order_status (OrderStatus): The current status of the order.
        side (Side): The side of the order.
        limit_price (float | None, optional): The existing limit price, if any.
        new_limit_price (float, optional): The proposed new limit price. Use `MODIFY_ORDER_SENTINEL` if unchanged.
        stop_loss (float | None, optional): The existing stop loss price, if any.
        new_stop_loss (float, optional): The proposed new stop loss price. Use `MODIFY_ORDER_SENTINEL` if unchanged.
        take_profit (float | None, optional): The existing take profit price, if any.
        new_take_profit (float, optional): The proposed new take profit price. Use `MODIFY_ORDER_SENTINEL` if unchanged.

    Returns:
        bool: False if validation failed, True if valid.
    """
    is_limit_order: bool = order_type == OrderType.LIMIT
    is_filled: bool = order_status == OrderStatus.FILLED

    sentinel = float("inf")
    updated_limit_price = sentinel
    updated_tp_price = sentinel
    updated_sl_price = sentinel

    if (
        is_limit_order
        and not is_filled
        and new_limit_price not in (MODIFY_ORDER_SENTINEL, None)
    ):
        updated_limit_price = new_limit_price
    if new_take_profit != MODIFY_ORDER_SENTINEL:
        updated_tp_price = new_take_profit
    if new_stop_loss != MODIFY_ORDER_SENTINEL:
        updated_sl_price = new_stop_loss

    tmp_stop_loss = float("-inf") if side == Side.BID else float("inf")
    if updated_sl_price != sentinel:
        if updated_sl_price is not None:
            tmp_stop_loss = updated_sl_price
    elif stop_loss is not None:
        tmp_stop_loss = stop_loss

    tmp_take_profit = float("inf") if side == Side.BID else float("-inf")
    if updated_tp_price != sentinel:
        if updated_tp_price is not None:
            tmp_take_profit = updated_tp_price
    elif take_profit is not None:
        tmp_take_profit = take_profit

    tmp_limit_price = sentinel
    if is_limit_order:
        if updated_limit_price != sentinel:
            tmp_limit_price = updated_limit_price
        else:
            tmp_limit_price = limit_price

    if is_limit_order:
        if is_filled and side == Side.BID and not (tmp_stop_loss < tmp_take_profit):
            return False

        if is_filled and side == Side.ASK and not (tmp_stop_loss > tmp_take_profit):
            return False

        if (
            not is_filled
            and side == Side.BID
            and not (tmp_stop_loss < tmp_limit_price <= cur_price < tmp_take_profit)
        ):
            return False

        if (
            not is_filled
            and side == Side.ASK
            and not (tmp_stop_loss > tmp_limit_price >= cur_price > tmp_take_profit)
        ):
            return False

    if is_filled and side == Side.BID and not (tmp_stop_loss < tmp_take_profit):
        return False

    if is_filled and side == Side.ASK and not (tmp_stop_loss > tmp_take_profit):
        return False

    if (
        not is_filled
        and side == Side.BID
        and not (tmp_stop_loss < cur_price < tmp_take_profit)
    ):
        return False

    if (
        not is_filled
        and side == Side.ASK
        and not (tmp_stop_loss > cur_price > tmp_take_profit)
    ):
        return False

    return True
