from enums import OrderType, Side, StrategyType


class Order:
    def __init__(
        self,
        id_: str,
        user_id: str,
        strategy_type: StrategyType,
        order_type: OrderType,
        side: Side,
        quantity: int,
        price: float | None = None,
    ):
        self.id = id_
        self.user_id = user_id
        self.strategy_type = strategy_type
        self.order_type= order_type
        self.side = side
        self.quantity = quantity
        self.executed_quantity = 0
        self.price = price
