from dataclasses import dataclass
from .managers import BalanceManager, OCOManager, OrderManager
from .orderbook import OrderBook


@dataclass
class OrderContext:
    """
    Context passed to order type handlers
    """

    orderbook: OrderBook
    engine: "BaseEngine"
    oco_manager: OCOManager | None = None
    order_manager: OrderManager | None = None
    balance_manager: BalanceManager | None = None
    
