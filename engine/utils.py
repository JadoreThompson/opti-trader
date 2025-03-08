import json

from datetime import datetime
from enum import Enum
from typing import TypedDict
from uuid import UUID

from engine.enums import PositionStatus
from enums import Side, OrderStatus
from .order import Order


calc_sell_pl = lambda amount, open_price, close_price: round(
    amount * (1 + (open_price - close_price) / open_price), 2
)
calc_buy_pl = lambda amount, open_price, close_price: round(
    (close_price / open_price) * amount, 2
)
dump_obj = lambda obj: json.dumps(
    {k: (str(v) if isinstance(v, (UUID, datetime)) else v) for k, v in obj.items()}
)


class EnginePayloadCategory(int, Enum):
    NEW = 0
    MODIFY = 1
    CLOSE = 2


class EnginePayload(TypedDict):
    category: EnginePayloadCategory
    content: dict


def calculate_upl(order: Order, new_price: float, ob) -> None:
    """
    Args:
        order (Order)
        price (float)
        ob (OrderBook)
    """
    # upl: float = None
    # # old_position_value: float = order.payload["filled_price"] * order.payload["quantity"]
    # new_position_value: float = (
    #     order.payload["filled_price"] * order.payload["standing_quantity"]
    # )

    # if order.payload["filled_price"] is None:
    #     return

    # if order.payload["side"] == Side.SELL:  # Must be a buy
    #     upl = calc_buy_pl(
    #         order.payload["unrealised_pnl"] + new_position_value,
    #         order.payload["filled_price"],
    #         price,
    #     )
    # else:
    #     upl = calc_sell_pl(
    #         order.payload["unrealised_pnl"] + new_position_value,
    #         order.payload["filled_price"],
    #         price,
    #     )

    # print("Upl - ",upl, "order id - ", order.payload['order_id'])
    # if order.payload["unrealised_pnl"] is not None:
    #     if upl <= order.payload["amount"] * -1:
    #         ob.remove(order, "all")
    #         order.payload["status"] = OrderStatus.CLOSED
    #         order.payload["closed_price"] = price
    #         order.payload["unrealised_pnl"] = 0
    #         order.payload["realised_pnl"] += upl
    #         return

    # order.payload["unrealised_pnl"] += upl
    # try:
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

    # upl_value = (
    #     order.payload["realised_pnl"]
    #     if order.position.status == PositionStatus.TOUCHED
    #     else order.payload["unrealised_pnl"]
    # )

    new_upl = round(-(pos_value - upl), 2)
    # cupl = order.payload['unrealised_pnl']
    if new_upl:
        if new_upl <= pos_value:
            ob.remove(order, "all")
            order.payload["status"] = OrderStatus.CLOSED
            order.payload["closed_price"] = new_price
            order.payload["unrealised_pnl"] = 0
            order.payload["realised_pnl"] += new_upl

        else:
            order.payload["unrealised_pnl"] = new_upl

        # print(
        #     "Order ID=",
        #     order.payload["order_id"],
        #     "Calculated UPL=",
        #     new_upl,
        #     "Assigned UPL=",
        #     order.payload["unrealised_pnl"],
        #     "Current Price=",
        #     new_price,
        #     "Filled Price=",
        #     order.payload["filled_price"],
        #     "Quantity=",
        #     order.payload["quantity"],
        #     "Side=",
        #     order.payload["side"],
        # )
        # else:
        #     print()
    # except Exception as e:
    #     print(type(e), str(e))
