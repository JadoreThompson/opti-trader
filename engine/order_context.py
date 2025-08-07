from dataclasses import dataclass

from .managers import SpotBalanceManager, OrderManager
from .orderbook import OrderBook
from .protocols import BalanceManagerProtocol, PayloadProtocol, StoreProtocol
from .stores import PayloadStore


@dataclass
class OrderContext:
    """
    Context passed to order type handlers
    """

    engine: "Engine"
    orderbook: OrderBook
    order_store: StoreProtocol
    payload_store: PayloadStore
    balance_manager: BalanceManagerProtocol
