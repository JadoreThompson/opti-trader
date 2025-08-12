from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import Orders
from enums import OrderStatus, StrategyType
from engine.models import (
    Command,
    CommandType,
    NewSingleOrder,
    CancelOrderCommand,
    ModifyOrderCommand,
)
from .models import OrderCreate, OrderModify
from engine_manager import command_queue


async def create_new_order(user_id: UUID, details: OrderCreate) -> dict:
    """
    Creates a command for a new order and puts it on the command queue.
    """
    # For now, we only support SINGLE strategy type from the API
    order_data = details.model_dump()
    order_data["user_id"] = str(user_id)  # Engine expects string IDs

    cmd_data = NewSingleOrder(
        strategy_type=StrategyType.SINGLE,
        instrument_id=details.instrument_id,
        order=order_data,
    )

    command = Command(command_type=CommandType.NEW_ORDER, data=cmd_data)
    command_queue.put(command)

    return {"order_id": details.order_id, "message": "Order accepteds"}


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
    command_queue.put(command)

    return order_id


async def cancel_all_orders(user_id: UUID, db_sess: AsyncSession) -> None:
    """Cancels all active orders for a user for a given instrument."""

    # Find all active orders
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
        # return {"cancelled_count": 0, "message": "No active orders found"}
        return

    # Dispatch a cancel command for each
    for order_id, instrument_id in orders_to_cancel:
        cmd_data = CancelOrderCommand(order_id=str(order_id), symbol=instrument_id)
        command = Command(command_type=CommandType.CANCEL_ORDER, data=cmd_data)
        command_queue.put(command)

    # return {
    #     "cancelled_count": len(orders_to_cancel),
    #     "message": "Cancel requests accepted",
    # }


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
    command_queue.put(command)

    return {"order_id": order_id, "message": "Modify request accepted"}
