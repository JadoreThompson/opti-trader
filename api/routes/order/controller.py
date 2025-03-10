import json
import sqlalchemy

from sqlalchemy import insert, select, update
from config import DB_LOCK, REDIS_CLIENT, SPOT_QUEUE_KEY, FUTURES_QUEUE_KEY
from db_models import Orders, Users
from enums import MarketType, OrderStatus, OrderType, Side
from engine.utils import EnginePayloadCategory, dump_obj
from engine.futures_engine import CloseOrderPayload as FuturesCloseOrderPayload
from engine.spot_engine import CloseOrderPayload as SpotCloseOrderPayload
from utils.db import get_db_session
from .models import FuturesCloseOrder, OrderWrite, SpotCloseOrder


def validate_order_details(
    price: float, req: OrderWrite | Orders, balance: float = None
) -> bool:
    """
    Args:
        price (float)
        req (OrderWrite | Orders)
        balance (Float)

    Raises:
        ValueError containing the error

    Returns:
        bool:
         - True Order validated
    """
    if isinstance(req, OrderWrite):
        try:
            if balance < req.quantity * price:
                raise ValueError("Insufficient balance to perform action")
        except TypeError:
            raise ValueError("Missing balance")

    if req.side == Side.SELL:
        if req.limit_price is not None:
            if req.limit_price <= price:
                raise ValueError("Limit price must be greater than market price")
        if req.take_profit is not None:
            if req.take_profit >= price:
                raise ValueError("TP must be less than market price")
        if req.stop_loss is not None:
            if req.stop_loss <= price:
                raise ValueError("SL must be greater than market price")

    if req.side == Side.BUY:
        if req.limit_price is not None:
            if req.limit_price >= price:
                raise ValueError("Limit price must be less than market price")
        if req.take_profit is not None:
            if req.take_profit <= price:
                raise ValueError("TP must be greater than market price")
        if req.stop_loss is not None:
            if req.stop_loss >= price:
                raise ValueError("SL must be less than market price")

    return True


async def enter_new_order(details: dict, user_id: str, balance: float) -> None:
    details["standing_quantity"] = details["quantity"]
    details["user_id"] = user_id

    async with DB_LOCK:
        async with get_db_session() as sess:
            balance -= details["amount"]
            await sess.execute(
                update(Users).values(balance=balance).where(Users.user_id == user_id)
            )
            res = await sess.execute(insert(Orders).values(details).returning(Orders))
            order = res.scalar()
            await sess.commit()

    payload = vars(order)
    del payload["_sa_instance_state"]
    payload["order_id"] = str(payload["order_id"])

    await REDIS_CLIENT.publish(
        (
            FUTURES_QUEUE_KEY
            if payload["market_type"] == MarketType.FUTURES
            else SPOT_QUEUE_KEY
        ),
        json.dumps(
            {"category": EnginePayloadCategory.NEW, "content": dump_obj(payload)}
        ),
    )


async def enter_modify_order(
    current_market_price: float,
    order: Orders,
    limit_price: float = None,
    take_profit: float = None,
    stop_loss: float = None,
):
    """Enters modify order into engine

    Args:
        current_market_price (float)
        order (Orders)
        limit_price (float, optional)
        take_profit (float, optional)
        stop_loss (float, optional)

    Raises:
        - raises ValueError if values contradict price or constraints
    """
    if order.status != OrderStatus.PENDING and limit_price is not None:
        raise ValueError("Cannot change limit price on already filled order")

    if order.standing_quantity != order.quantity:
        raise ValueError(
            "Cannot change take profit or stop loss on partially closed order"
        )

    if take_profit is not None:
        order.take_profit = take_profit

    if stop_loss is not None:
        order.stop_loss = stop_loss

    if order.order_type == OrderType.LIMIT and limit_price is not None:
        order.limit_price = limit_price

    validate_order_details(current_market_price, order)

    if order.market_type == MarketType.FUTURES:
        payload = vars(order)
        del payload["_sa_instance_state"]
        payload["order_id"] = str(payload["order_id"])
        await REDIS_CLIENT.publish(
            FUTURES_QUEUE_KEY,
            json.dumps(
                {"category": EnginePayloadCategory.MODIFY, "content": dump_obj(payload)}
            ),
        )


async def get_futures_close_order_details(
    user_id: str, payload: FuturesCloseOrder
) -> dict:
    """
    Fetches the order with the passed order id, and returns
    the additional kwargs to be passed into enter_close_order

    Args:
        order_id (str)
        user_id (str)

    Raises:
        ValueError: Order doesn't exist or isn't of adequate status

    Returns:
        dict: Additional kwargs
    """
    async with get_db_session() as sess:
        res = await sess.execute(
            select(Orders.instrument).where(
                (Orders.order_id == payload.order_id)
                & (Orders.user_id == user_id)
                & (
                    Orders.status.not_in(
                        (
                            OrderStatus.PENDING,
                            OrderStatus.PARTIALLY_FILLED,
                            OrderStatus.PARTIALLY_CLOSED,
                            OrderStatus.CLOSED,
                        )
                    )
                )
                & (Orders.market_type == MarketType.FUTURES)
            )
        )

        details = res.first()

    if details is None:
        raise ValueError("Cannot perform action on partiall or closed orders")

    return {"instrument": details[0], "order_id": payload.order_id}


async def get_spot_close_order_details(
    user_id: str,
    payload: SpotCloseOrder,
) -> dict:
    running_total = (
        sqlalchemy.sql.func.sum(Orders.standing_quantity)
        .over(order_by=Orders.standing_quantity.asc())
        .label("running_total")
    )

    ordered_rows_subquery = (
        select(Orders.order_id, Orders.standing_quantity, running_total)
        .where(
            (Orders.user_id == user_id)
            & (Orders.status.in_((OrderStatus.PARTIALLY_CLOSED, OrderStatus.FILLED)))
        )
        .subquery()
    )

    min_running_total_subquery = (
        select(sqlalchemy.sql.func.min(ordered_rows_subquery.c.running_total))
        .where(ordered_rows_subquery.c.running_total >= payload.quantity)
        .scalar_subquery()
    )

    async with get_db_session() as sess:
        res = await sess.execute(
            select(ordered_rows_subquery.c.order_id).where(
                (ordered_rows_subquery.c.running_total >= payload.quantity)
                & (ordered_rows_subquery.c.running_total == min_running_total_subquery)
            )
        )

        details = res.all()

    if not details:
        raise ValueError("Insuffucient assets")

    return {
        "instrument": payload.instrument,
        "quantity": payload.quantity,
        "order_ids": tuple((str(item[0]) for item in details)),
    }


async def enter_close_order(
    market_type: MarketType,
    details: FuturesCloseOrderPayload | SpotCloseOrderPayload,
) -> None:

    await REDIS_CLIENT.publish(
        FUTURES_QUEUE_KEY if market_type == MarketType.FUTURES else SPOT_QUEUE_KEY,
        json.dumps(
            {
                "category": EnginePayloadCategory.CLOSE,
                "content": dump_obj(details),
            }
        ),
    )
