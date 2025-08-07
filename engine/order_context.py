from dataclasses import dataclass
from .managers import BalanceManager, OrderManager
from .orderbook import OrderBook


@dataclass
class OrderContext:
    """
    Context passed to order type handlers
    """

    orderbook: OrderBook
    engine: "Engine"
    order_manager: OrderManager | None = None
    balance_manager: BalanceManager | None = None
