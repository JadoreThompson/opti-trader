import json

from datetime import datetime
from uuid import UUID
from enums import Side, OrderStatus
from .order import Order


# def calc_sell_pnl(amount: float, open_price: float, close_price: float) -> float:
#     """Returns the new value of the amount for sell order"""
#     try:
#         return round(amount * (1 + (open_price - close_price) / open_price), 2)
#     except ZeroDivisionError:
#         return 0.0


def calc_sell_pnl(amount: float, open_price: float, close_price: float) -> float:
    """Returns the PnL for a sell order"""
    try:
        return round(amount * (1 + (open_price - close_price) / open_price) - amount, 2)
    except ZeroDivisionError:
        return 0.0

    # def calc_buy_pnl(amount: float, open_price: float, close_price: float) -> float:
    """Returns the new value of the amount for buy order"""
    # try:
    #     return round((close_price / open_price) * amount, 2)
    # except ZeroDivisionError:
    #     return 0.0


def calc_buy_pnl(amount: float, open_price: float, close_price: float) -> float:
    """Returns the PnL for a buy order"""
    try:
        return round((close_price / open_price) * amount - amount, 2)
    except ZeroDivisionError:
        return 0.0


def dump_obj(obj: dict) -> str:
    """
    Handles the dumping of a dictionary, converting UUID and datetime fields to strings

    Args:
        obj (dict) - Non nested dictionary
    """
    return json.dumps(
        {k: (str(v) if isinstance(v, (UUID, datetime)) else v) for k, v in obj.items()}
    )


def update_upl(order: Order, new_price: float) -> None:
    """
    Updates the order's unrealised pnl field. If the unrealised
    pnl is the equivalent to the negative of the position value.
    The order's status is set to CLOSED and other relating fields
    are updated.

    Args:
        order (Order): Order
        new_price (float): Current market price.
    """
    filled_price = order.payload.get("filled_price")
    standing_qty = order.payload.get("standing_quantity")

    if filled_price is None or standing_qty == 0:
        return

    pos_value = filled_price * standing_qty

    side = order.payload["side"]
    if side == Side.ASK:
        pnl = calc_sell_pnl(pos_value, filled_price, new_price)
    else:
        pnl = calc_buy_pnl(pos_value, filled_price, new_price)

    upl = round(pnl, 2)

    if upl <= -pos_value:
        order.payload["status"] = OrderStatus.CLOSED
        order.payload["closed_at"] = datetime.now()
        order.payload["closed_price"] = new_price
        order.payload["standing_quantity"] = 0
        order.payload["unrealised_pnl"] = 0
        order.payload["realised_pnl"] += upl

    order.payload["unrealised_pnl"] = upl
