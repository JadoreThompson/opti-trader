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


# DANGER !!!
# def calculate_upl(order: Order, new_price: float, ob) -> None:
#     """
#     Calculates the Unrealised PnL for a given order.
#     If the calcualted pnl equals to the negative value for the
#     value of the position, it's assigned order status CLOSED,
#     standing quantity and unrealised pnl of 0, realised pnl
#     is then calculated.

#     Args:
#         order (Order)
#         new_price (float)
#         ob (OrderBook)
#     """
#     if order.payload["filled_price"] is None:
#         return False

#     pos_value = order.payload["filled_price"] * order.payload["standing_quantity"]

#     if order.payload["side"] == Side.ASK:
#         upl = calc_sell_pnl(pos_value, order.payload["filled_price"], new_price)
#     else:
#         upl = calc_buy_pnl(pos_value, order.payload["filled_price"], new_price)

#     new_upl = round(-(pos_value - upl), 2)

#     if new_upl:
#         if new_upl <= -pos_value:
#             # ob.remove_all(order)
#             order.payload["status"] = OrderStatus.CLOSED
#             order.payload["closed_at"] = datetime.now()
#             order.payload["closed_price"] = new_price
#             order.payload["standing_quantity"] = order.payload["unrealised_pnl"] = 0
#             order.payload["realised_pnl"] += new_upl
#             return True
#         else:
#             order.payload["unrealised_pnl"] = new_upl

#     return False
from datetime import datetime
from decimal import Decimal  # if you're working with money

def calculate_upl(order: Order, new_price: float, ob) -> bool:
    """
    Calculates Unrealised PnL for a given order.
    Closes the order if PnL drops to total loss.

    Args:
        order (Order)
        new_price (float)
        ob (OrderBook)
    """
    filled_price = order.payload.get("filled_price")
    standing_qty = order.payload.get("standing_quantity")

    if filled_price is None or standing_qty == 0:
        return False

    pos_value = filled_price * standing_qty

    side = order.payload["side"]
    if side == Side.ASK:
        pnl = calc_sell_pnl(pos_value, filled_price, new_price)
    else:
        pnl = calc_buy_pnl(pos_value, filled_price, new_price)

    # Final unrealised PnL value
    upl = round(pnl, 2)

    # If position is fully lost
    if upl <= -pos_value:
        order.payload["status"] = OrderStatus.CLOSED
        order.payload["closed_at"] = datetime.now()
        order.payload["closed_price"] = new_price
        order.payload["standing_quantity"] = 0
        order.payload["unrealised_pnl"] = 0
        order.payload["realised_pnl"] += upl
        return True

    # Still open, update UPL
    order.payload["unrealised_pnl"] = upl
    return False
