from ..orderbook import OrderBook

class Base:
    def __init__(self, data: dict) -> None:
        self._data = data
    
    def remove_from_orderbook(self, orderbook: OrderBook) -> None: ...
    
    def append_to_orderbook(self, orderbook: OrderBook, price: float=None) -> None: ...
    
    def reduce_standing_quantity(self, quantity: int) -> None: ...
    
    def alter_position(self, orderbook: OrderBook, price: float=None) -> None: ...
    """Alters the position of the order within the orderbook"""
    
    @property
    def data(self) -> dict:
        return self._data
    