import logging

from uuid import uuid4, UUID

from enums import OrderStatus, Side
from trading_engine.orderbook import OrderBook
from .base import Base

logger = logging.getLogger(__name__)

class _FuturesContract(Base):
    def __init__(
        self, 
        data: dict, 
        price: float, 
        tag: str=None, 
        side: Side=None
    ) -> None:
        self.price = price
        self.position = None
        
        self._tag = tag
        self._contract_id = uuid4()
        self._data = data
        self._side: Side = side or data['side']
        self._status: OrderStatus = data['status']
        self._standing_quantity: int = data['standing_quantity']
        self._quantity: int = data['quantity']
        self._margin: float = self._calculate_margin()
        
    def remove_from_orderbook(self, orderbook: OrderBook) -> None:
        try:
            if self.side == Side.LONG:
                orderbook.bids[self.price].remove(self)
            else:
                orderbook.asks[self.price].remove(self)
        except (KeyError, ValueError) as e:
            pass
    
    def reduce_standing_quantity(self, quantity: int) -> None:
        if self._standing_quantity - quantity <= 0:
            self._standing_quantity = self.data['standing_quantity'] = 0
            self.status = OrderStatus.FILLED
        else:
            self._standing_quantity -= quantity
            
        self._calculate_margin()
        
    def append_to_orderbook(self, orderbook: OrderBook, price: float = None) -> None:
        if not price:
            price = self.price
            
        if self._side == Side.LONG:
            orderbook.bids[price].append(self)
        else:
            orderbook.asks[price].append(self)
    
    def _calculate_margin(self):
        self._margin = self._standing_quantity * self.price
            
    def __repr__(self) -> str:
        return f'Contract(side={self.side})'

    def __str__(self) -> str:
        return self.__repr__()
            
    @property
    def contract_id(self) -> UUID:
        return self._contract_id
    
    @property
    def data(self) -> dict:
        return self._data
    
    @property
    def side(self) -> Side:
        return self._side

    @property
    def status(self) -> OrderStatus:
        return self._status
    
    @status.setter
    def status(self, value: OrderStatus) -> None:
        self._status = self.data['status'] = value
        
    @property
    def standing_quantity(self) -> int:
        return self._standing_quantity

    @property
    def margin(self) -> float:
        return self._margin
    
    @property
    def quantity(self) -> int:
        return self._quantity

    @property
    def tag(self):
        return self._tag