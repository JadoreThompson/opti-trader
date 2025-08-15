from enum import Enum
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import CASH_ESCROW_HKEY, REDIS_CLIENT_ASYNC
from db_models import AssetBalances, Orders, Trades, Users
from enums import OrderStatus, OrderType, Side, StrategyType
from engine.models import (
    Command,
    CommandType,
    NewOCOOrder,
    NewOTOCOOrder,
    NewOTOOrder,
    NewSingleOrder,
    CancelOrderCommand,
    ModifyOrderCommand,
)
from utils.utils import get_instrument_escrows_hkey
from .models import (
    OCOOrderCreate,
    OTOCOOrderCreate,
    OTOOrderCreate,
    OrderCreate,
    OrderModify,
)
from config import COMMAND_QUEUE


async def handle_escrow(
    user_id: str | UUID,
    instrument_id: str,
    quantity: float,
    price: float,
    side: Side,
    db_sess: AsyncSession,
) -> None:
    """
    Handles the escrow process for orders.
    To be used when the order_type is MARKET.

    Raises:
        ValueError: Invalid cash balance.
        ValueError: Invalid asset balance.
    """
    if side == Side.BID:
        total_value = quantity * price
        res = await db_sess.execute(
            select(Users.cash_balance - Users.escrow_balance).where(
                Users.user_id == user_id
            )
        )
        remaing_balance = res.scalar()

        if remaing_balance < total_value:
            raise ValueError("Invalid cash balance.")

        await db_sess.execute(
            update(Users)
            .where(Users.user_id == user_id)
            .values(escrow_balance=Users.escrow_balance + total_value)
        )

        await REDIS_CLIENT_ASYNC.hincrbyfloat(CASH_ESCROW_HKEY, user_id, total_value)
        return

    res = await db_sess.execute(
        select(AssetBalances.balance - AssetBalances.escrow_balance).where(
            AssetBalances.user_id == user_id,
            AssetBalances.instrument_id == instrument_id,
        )
    )
    remaing_balance = res.scalar()
    if remaing_balance is None or remaing_balance < quantity:
        raise ValueError("Invalid asset balance.")

    await db_sess.execute(
        update(AssetBalances)
        .where(
            AssetBalances.user_id == user_id,
            AssetBalances.instrument_id == instrument_id,
        )
        .values(escrow_balance=AssetBalances.escrow_balance + quantity)
    )
    await REDIS_CLIENT_ASYNC.hincrbyfloat(
        get_instrument_escrows_hkey(instrument_id), user_id, quantity
    )


async def fetch_last_trade_price(
    instrument_id: str, db_sess: AsyncSession
) -> float | None:
    res = await db_sess.execute(
        select(Trades.price)
        .where(Trades.instrument_id == instrument_id)
        .order_by(Trades.executed_at.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


async def create_order(
    user_id: str, details: OrderCreate, db_sess: AsyncSession
) -> str:
    # if details.order_type == OrderType.MARKET:
    #     entry_price = await fetch_last_trade_price(details.instrument_id, db_sess)
    #     if not entry_price:
    #         raise ValueError(
    #             f"No last trade price for market order on {details.instrument_id}"
    #         )

    #     await handle_escrow(
    #         user_id,
    #         details.instrument_id,
    #         details.quantity,
    #         entry_price,
    #         details.side,
    #         db_sess,
    #     )
    order_data = details.model_dump()
    order_data["price"] = 100

    res = await db_sess.execute(
        insert(Orders)
        .values(
            user_id=user_id,
            **{
                k: (v.value if isinstance(v, Enum) else v)
                for k, v in order_data.items()
            },
        )
        .returning(Orders)
    )
    order = res.scalar()
    await db_sess.flush()

    cmd_data = NewSingleOrder(
        strategy_type=StrategyType.SINGLE,
        instrument_id=details.instrument_id,
        order=order.dump(),
    )

    command = Command(command_type=CommandType.NEW_ORDER, data=cmd_data)
    return str(order.order_id)


async def create_oco_order(
    user_id: str, details: OCOOrderCreate, db_sess: AsyncSession
) -> list[str]:
    """Creates two orders for an OCO strategy and dispatches a command to the engine."""
    db_orders = []
    instrument_id = details.legs[0].instrument_id

    for leg_details in details.legs:
        entry_price = leg_details.limit_price or leg_details.stop_price
        if entry_price is None:
            raise ValueError("OCO leg must have a limit_price or stop_price.")

        order_data = leg_details.model_dump()
        res = await db_sess.execute(
            insert(Orders)
            .values(
                user_id=user_id,
                **{
                    k: (v.value if isinstance(v, Enum) else v)
                    for k, v in order_data.items()
                },
            )
            .returning(Orders)
        )
        db_orders.append(res.scalar())

    await db_sess.flush()

    cmd_data = NewOCOOrder(
        strategy_type=StrategyType.OCO,
        instrument_id=instrument_id,
        legs=[o.dump() for o in db_orders],
    )

    command = Command(command_type=CommandType.NEW_ORDER, data=cmd_data)
    COMMAND_QUEUE.put_nowait(command)

    return [str(o.order_id) for o in db_orders]


async def create_oto_order(
    user_id: str, details: OTOOrderCreate, db_sess: AsyncSession
) -> list[str]:
    """Creates a parent and child order for an OTO strategy."""
    parent_details = details.parent
    instrument_id = parent_details.instrument_id

    entry_price = parent_details.limit_price or parent_details.stop_price
    if parent_details.order_type == OrderType.MARKET:
        entry_price = await fetch_last_trade_price(instrument_id, db_sess)
        if not entry_price:
            raise ValueError(f"No last trade price for market order on {instrument_id}")

    parent_res = await db_sess.execute(
        insert(Orders)
        .values(
            user_id=user_id,
            **{
                k: (v.value if isinstance(v, Enum) else v)
                for k, v in parent_details.model_dump().items()
            },
        )
        .returning(Orders)
    )
    parent_order = parent_res.scalar()

    child_details = details.child
    child_res = await db_sess.execute(
        insert(Orders)
        .values(
            user_id=user_id,
            **{
                k: (v.value if isinstance(v, Enum) else v)
                for k, v in child_details.model_dump().items()
            },
        )
        .returning(Orders)
    )
    child_order = child_res.scalar()

    await db_sess.flush()

    cmd_data = NewOTOOrder(
        strategy_type=StrategyType.OTO,
        instrument_id=instrument_id,
        parent=parent_order.dump(),
        child=child_order.dump(),
    )

    command = Command(command_type=CommandType.NEW_ORDER, data=cmd_data)
    COMMAND_QUEUE.put_nowait(command)

    return [str(parent_order.order_id), str(child_order.order_id)]


async def create_otoco_order(
    user_id: str, details: OTOCOOrderCreate, db_sess: AsyncSession
) -> list[str]:
    """Creates a parent and two child orders for an OTOCO strategy."""
    parent_details = details.parent
    instrument_id = parent_details.instrument_id

    entry_price = parent_details.limit_price or parent_details.stop_price
    if parent_details.order_type == OrderType.MARKET:
        entry_price = await fetch_last_trade_price(instrument_id, db_sess)
        if not entry_price:
            raise ValueError(f"No last trade price for market order on {instrument_id}")

        await handle_escrow(
            user_id,
            instrument_id,
            parent_details.quantity,
            entry_price,
            parent_details.side,
            db_sess,
        )

    parent_res = await db_sess.execute(
        insert(Orders)
        .values(
            user_id=user_id,
            **{
                k: (v.value if isinstance(v, Enum) else v)
                for k, v in parent_details.model_dump().items()
            },
        )
        .returning(Orders)
    )
    parent_order = parent_res.scalar()

    oco_leg_orders = []
    for leg_details in details.oco_legs:
        res = await db_sess.execute(
            insert(Orders)
            .values(
                user_id=user_id,
                **{
                    k: (v.value if isinstance(v, Enum) else v)
                    for k, v in leg_details.model_dump().items()
                },
            )
            .returning(Orders)
        )
        oco_leg_orders.append(res.scalar())

    await db_sess.flush()

    cmd_data = NewOTOCOOrder(
        strategy_type=StrategyType.OTOCO,
        instrument_id=instrument_id,
        parent=parent_order.dump(),
        oco_legs=[o.dump() for o in oco_leg_orders],
    )

    command = Command(command_type=CommandType.NEW_ORDER, data=cmd_data)
    COMMAND_QUEUE.put_nowait(command)

    return [str(parent_order.order_id)] + [str(o.order_id) for o in oco_leg_orders]


async def cancel_order(
    user_id: UUID, order_id: UUID, db_sess: AsyncSession
) -> str | None:
    """
    Creates a command to cancel an order.
    """
    res = await db_sess.execute(
        select(Orders).where(Orders.order_id == order_id, Orders.user_id == user_id)
    )
    order = res.scalar_one_or_none()
    if not order:
        return

    cmd_data = CancelOrderCommand(order_id=str(order_id), symbol=order.instrument_id)
    command = Command(command_type=CommandType.CANCEL_ORDER, data=cmd_data)
    COMMAND_QUEUE.put_nowait(command)

    return str(order.order_id)


async def cancel_all_orders(user_id: UUID, db_sess: AsyncSession) -> None:
    """Cancels all active orders for a user for a given instrument."""
    result = await db_sess.execute(
        select(Orders.order_id, Orders.instrument_id).where(
            Orders.user_id == user_id,
            Orders.status.in_(
                (OrderStatus.PENDING.value, OrderStatus.PARTIALLY_FILLED.value)
            ),
        )
    )
    orders_to_cancel = result.all()

    if not orders_to_cancel:
        return

    for order_id, instrument_id in orders_to_cancel:
        cmd_data = CancelOrderCommand(order_id=str(order_id), symbol=instrument_id)
        command = Command(command_type=CommandType.CANCEL_ORDER, data=cmd_data)
        COMMAND_QUEUE.put_nowait(command)


async def modify_order(
    user_id: UUID, order_id: UUID, details: OrderModify, db_sess: AsyncSession
) -> dict:
    """Creates a command to modify an order."""
    order = await db_sess.get(Orders, order_id)
    if not order or order.user_id != user_id:
        return None

    cmd_data = ModifyOrderCommand(
        order_id=str(order_id),
        symbol=order.instrument_id,
        limit_price=details.limit_price,
        stop_price=details.stop_price,
    )
    command = Command(command_type=CommandType.MODIFY_ORDER, data=cmd_data)
    COMMAND_QUEUE.put_nowait(command)

    return {"order_id": str(order_id), "message": "Modify request accepted"}
