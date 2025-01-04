import logging

from uuid import uuid4, UUID

from enums import OrderStatus, Side
from trading_engine.orderbook import OrderBook
from .base import Base

logger = logging.getLogger(__name__)

class _FuturesContract(Base):
    def __init__(self, data: dict) -> None:
        self.price = \
            data['entry_price'] if data.get('entry_price', None) is not None \
            else data['limit_price']
        
        self._contract_id = uuid4()
        self._data = data
        self._side: Side = data['side']
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
            logger.error('{} - {}'.format(type(e), str(e)))
            pass
    
    def append_to_orderbook(self, orderbook: OrderBook) -> None:
        if self.side == Side.LONG:
            orderbook.bids.setdefault(self.price, [])
            orderbook.bids[self.price].append(self)
        else:
            orderbook.asks.setdefault(self.price, [self])
            orderbook.asks[self.price].append(self)
    
    def reduce_standing_quantity(self, quantity: int) -> None:
        if self._standing_quantity - quantity <= 0:
            self._standing_quantity = self.data['standing_quantity'] = 0
            self.status = OrderStatus.FILLED
        else:
            self._standing_quantity -= quantity
            
        self._calculate_margin()
            
    def _calculate_margin(self):
        self._margin = self._standing_quantity * self.price
            
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
    def status(self, status: OrderStatus) -> None:
        self._status = self.data['status'] = status
        
    @property
    def standing_quantity(self) -> int:
        return self._standing_quantity

    @property
    def margin(self) -> float:
        return self._margin
    
    @property
    def quantity(self) -> int:
        return self._quantity