from sqlalchemy import insert, select, update
from config import DB_LOCK
from db_models import Orders, Users
from enums import MarketType, OrderStatus, OrderType, Side
from engine.utils import EnginePayloadCategory
from utils.db import get_db_session
from .models import OrderWrite
from ...config import FUTURES_QUEUE


def validate_order_details(
    price: float, order: OrderWrite | Orders, balance: float=None
) -> bool:
    """
    Args:
        price (float)
        order (OrderWrite | Orders)
        balance (Float)

    Raises:
        ValueError containing the error

    Returns:
        bool:
         - True Order validated
    """
    if isinstance(order, OrderWrite):
        try:
            if balance < order.quantity * price:
                raise ValueError("Insufficient balance to perform action")
        except TypeError:
            raise ValueError('Missing balance')

    if order.side == Side.SELL:
        if order.limit_price is not None:
            if order.limit_price <= price:
                raise ValueError("Limit price must be greater than market price")
        if order.take_profit is not None:
            if order.take_profit >= price:
                raise ValueError("TP must be less than market price")
        if order.stop_loss is not None:
            if order.stop_loss <= price:
                raise ValueError("SL must be greater than market price")

    if order.side == Side.BUY:
        if order.limit_price is not None:
            if order.limit_price >= price:
                raise ValueError("Limit price must be less than market price")
        if order.take_profit is not None:
            if order.take_profit <= price:
                raise ValueError("TP must be greater than market price")
        if order.stop_loss is not None:
            if order.stop_loss >= price:
                raise ValueError("SL must be less than market price")

    return True


async def enter_new_order(details: dict, user_id: str, balance: float) -> None:
    details["standing_quantity"] = details["quantity"]
    details["user_id"] = user_id

    async with DB_LOCK:
        async with get_db_session() as sess:
            # res = await sess.execute(
            #     select(Users.balance).where(Users.user_id == user_id)
            # )

            # if balance < 0:
            #     raise ValueError("Insufficient balance")

            balance -= details["amount"]
            await sess.execute(
                update(Users).values(balance=balance).where(Users.user_id == user_id)
            )
            res = await sess.execute(insert(Orders).values(details).returning(Orders))
            order = res.scalar()
            await sess.commit()

    if details["market_type"] == MarketType.FUTURES:
        payload = vars(order)
        del payload["_sa_instance_state"]
        payload["order_id"] = str(payload["order_id"])
        # print("Pushing this payload to the futures engine - ", payload)
        FUTURES_QUEUE.put_nowait(
            {"category": EnginePayloadCategory.NEW, "content": payload}
        )


def enter_modify_order(
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
        FUTURES_QUEUE.put_nowait(
            {"category": EnginePayloadCategory.MODIFY, "content": payload}
        )


def enter_close_order(
    order_id: str, market_type: MarketType, instrument: str, current_price: float
) -> None:
    if market_type == MarketType.FUTURES:
        FUTURES_QUEUE.put_nowait(
            {
                "category": EnginePayloadCategory.CLOSE,
                "content": {
                    "order_id": order_id,
                    "instrument": instrument,
                    "price": current_price,
                },
            }
        )
