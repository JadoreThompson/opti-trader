import json

from datetime import datetime
from enum import Enum
from typing import TypedDict
from uuid import UUID

from enums import Side, OrderStatus
from .order import Order


def calc_sell_pl(amount: float, open_price: float, close_price: float) -> float:
    """Returns the new value of the amount for sell order"""
    return round(amount * (1 + (open_price - close_price) / open_price), 2)


def calc_buy_pl(amount: float, open_price: float, close_price: float) -> float:
    """Returns the new value of the amount for buy order"""
    return round((close_price / open_price) * amount, 2)


def dump_obj(obj: dict) -> str:
    """
    Handles the dumping of a dictionary, converting UUID and datetime fields to strings

    Args:
        obj (dict) - Non nested dictionary
    """
    return json.dumps(
        {k: (str(v) if isinstance(v, (UUID, datetime)) else v) for k, v in obj.items()}
    )


class EnginePayloadCategory(int, Enum):
    """All categories of payloads to be sent to the engine"""

    NEW = 0
    MODIFY = 1
    CLOSE = 2


class EnginePayload(TypedDict):
    """Payload Schema for submitting requests to the engine"""

    category: EnginePayloadCategory
    content: dict


def calculate_upl(order: Order, new_price: float, ob) -> None:
    """
    Calculates the Unrealised PnL for a given order.
    If the calcualted pnl equals to the negative value for the
    value of the position, it's assigned order status CLOSED, 
    standing quantity and unrealised pnl of 0, realised pnl is then calculated.
    
    Args:
        order (Order)
        price (float)
        ob (OrderBook)
    """
    if order.payload["filled_price"] is None:
        return

    pos_value = order.payload["filled_price"] * order.payload["standing_quantity"]

    if order.payload["side"] == Side.SELL:
        upl = calc_sell_pl(
            pos_value,
            order.payload["filled_price"],
            new_price,
        )

    else:
        upl = calc_buy_pl(
            pos_value,
            order.payload["filled_price"],
            new_price,
        )

    new_upl = round(-(pos_value - upl), 2)
    
    if new_upl:
        if new_upl <= -pos_value:
            ob.remove_all(order)
            order.payload["status"] = OrderStatus.CLOSED
            order.payload["closed_at"] = datetime.now()
            order.payload["closed_price"] = new_price
            order.payload["standing_quantity"] = order.payload["unrealised_pnl"] = 0
            order.payload["realised_pnl"] += new_upl

        else:
            order.payload["unrealised_pnl"] = new_upl
