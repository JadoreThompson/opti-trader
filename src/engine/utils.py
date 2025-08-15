from enums import OrderType, Side
from .orderbook import OrderBook


def get_price_key(ot: OrderType) -> str | None:
    ot = OrderType(ot)
    m = {
        OrderType.MARKET: "price",
        OrderType.LIMIT: "limit_price",
        OrderType.STOP: "stop_price",
    }

    return m.get(ot)


def limit_crossable(price: float, side: Side, ob: OrderBook) -> bool:
    return (side == Side.BID and ob.price is not None and price >= ob.price) or (
        side == Side.ASK and ob.price is not None and price <= ob.price
    )


def stop_crossable(price: float, side: Side, ob: OrderBook) -> bool:
    return (side == Side.BID and ob.price is not None and price <= ob.price) or (
        side == Side.ASK and ob.price is not None and price >= ob.price
    )
