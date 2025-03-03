from enums import Side, OrderStatus
from .order import Order

calc_sell_pl = lambda amount, open_price, close_price: round(
    amount * (1 + (open_price - close_price) / open_price), 2
)
calc_buy_pl = lambda amount, open_price, close_price: round(
    (close_price / open_price) * amount, 2
)


def calculate_upl(order: Order, price: float, ob) -> None:
    """
    Args:
        order (Order)
        price (float)
        ob (OrderBook)
    """
    upl: float = None

    if order.payload["filled_price"] is None:
        return

    if order.payload["side"] == Side.SELL:  # Must be a buy
        upl = calc_buy_pl(order.payload["amount"], order.payload["filled_price"], price)
    else:
        upl = calc_sell_pl(
            order.payload["amount"],
            order.payload["filled_price"],
            price,
        )
    if order.payload["unrealised_pnl"] is not None:
        if upl <= order.payload["amount"] * -1:
            ob.remove(order, "all")
            order.payload["status"] = OrderStatus.CLOSED
            order.payload["closed_price"] = price
            order.payload["unrealised_pnl"] = 0
            order.payload["realised_pnl"] = upl
            return

    order.payload["unrealised_pnl"] = upl
