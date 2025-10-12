from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import Orders
from engine.models import (
    Command,
    CommandType,
    CancelOrderCommand,
    ModifyOrderCommand,
)
from enums import OrderStatus
from .models import OrderModify
from config import COMMAND_QUEUE


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
    user_id: str, order_id: UUID, details: OrderModify, db_sess: AsyncSession
) -> dict:
    """Creates a command to modify an order."""
    order = await db_sess.get(Orders, order_id)
    if not order or str(order.user_id) != user_id:
        return None

    kw = {}
    if details.stop_price is not None:
        kw["stop_price"] = details.stop_price
    elif details.limit_price is not None:
        kw["limit_price"] = details.limit_price

    cmd_data = ModifyOrderCommand(
        order_id=str(order_id), symbol=order.instrument_id, **kw
    )
    command = Command(command_type=CommandType.MODIFY_ORDER, data=cmd_data)
    COMMAND_QUEUE.put_nowait(command)

    return {"order_id": str(order_id), "message": "Modify request accepted"}
