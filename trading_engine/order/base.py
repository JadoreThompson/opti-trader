from typing import override
from ..orderbook import OrderBook

class Base:
    def __init__(self, data: dict) -> None:
        self._data = data
    
    @override
    def remove_from_orderbook(self, orderbook: OrderBook) -> None: ...
    
    @override
    def append_to_orderbook(self, orderbook: OrderBook, price: float=None) -> None: ...
    
    @override
    def reduce_standing_quantity(self, quantity: int) -> None: ...
    
    @property
    def data(self) -> dict:
        return self._data
    