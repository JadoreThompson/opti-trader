from enums import OrderType


def get_price_key(value: OrderType) -> str | None:
    m = {
        OrderType.LIMIT: "limit_price",
        OrderType.MARKET: "price",
        OrderType.STOP: "stop_price",
        OrderType.TAKE_PROFIT: "take_profit",
        OrderType.STOP_LOSS: "stop_loss",
    }

    return m.get(value)
