from ..orders import SpotOrder

class OrderManager:
    """
    Store a new SpotOrder instance with Tag Tag.ENTRY.

    The OrdereManager allows the matching engine to retain 
    a reference to active or recently active orders so they 
    can be retrieved later e.g. to modify, cancel, or update 
    take-profit/stop-loss instructions.

    Note:
        - This store does not necessarily reflect every order 
          currently in the order book. Even after an order is 
          fully filled, we may keep it here to maintain access 
          it's attributes such as oco_id in case the client wants
          to perform cancellations and modifications.
    """
    def __init__(self) -> None:
        self._orders: dict[str, SpotOrder] = {}

    def append(self, order: SpotOrder) -> None:        
        if order.id in self._orders:
            raise ValueError(f"Order with ID {order.id} already exists.")
        
        self._orders[order.id] = order
        return True
    
    def get(self, order_id: str) -> SpotOrder | None:
        return self._orders.get(order_id)

    def remove(self, order_id: str) -> None:
        self._orders.pop(order_id, None)

