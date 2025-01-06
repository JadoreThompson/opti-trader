import logging

from datetime import datetime
from uuid import uuid4, UUID

from enums import OrderStatus, Side
from trading_engine.orderbook import OrderBook
from .base import Base
from ..enums import Tag

logger = logging.getLogger(__name__)

class _FuturesContract(Base):
    def __init__(
        self, 
        data: dict, 
        price: float, 
        tag: str=None, 
        side: Side=None,
        **kwargs,
    ) -> None:
        self.price = price
        self.position = None
        
        self._tag = tag
        self._contract_id = uuid4()
        self._data = data
        self._side: Side = side or data['side']
        self._order_status: OrderStatus = data['order_status']
        self._standing_quantity = self._quantity = data['quantity']
        self._margin: float = self._calculate_margin()
        
        if tag == Tag.ORPHAN:
            if 'orphan_quantity' not in kwargs:
                raise ValueError("Must pass orphan_quantity for orphan contracts")
            self._standing_quantity = kwargs['orphan_quantity']
        
    def remove_from_orderbook(self, orderbook: OrderBook, category: str=None) -> None:
        """

        Args:
            orderbook (OrderBook):
            category (str, optional): Redundant param.
        """
        try:
            if self.side == Side.LONG:
                orderbook.bids[self.price].remove(self)
            else:
                orderbook.asks[self.price].remove(self)
        except (KeyError, ValueError):
            pass
    
    def reduce_standing_quantity(self, quantity: int) -> None:
        clause: bool = self._standing_quantity - quantity <= 0
        
        if self._tag == Tag.ENTRY:
            if clause:
                self._standing_quantity = 0
                self.data['standing_quantity'] = self.data['quantity']
                self.order_status = OrderStatus.FILLED
                print('ENTRY CONTRACT FILLED, STANDING_QUANTITY:', self.data['standing_quantity'],)
            else:
                self._standing_quantity = self.data['standing_quantity'] = self._standing_quantity - quantity
                self.order_status = OrderStatus.PARTIALLY_FILLED
        
        elif self._tag in [Tag.TAKE_PROFIT, Tag.STOP_LOSS]:
            if clause:
                self._standing_quantity = self.data['standing_quantity'] = 0
                self.order_status = OrderStatus.CLOSED
            else:
                self._standing_quantity = self.data['standing_quantity'] = self._standing_quantity - quantity
                self.order_status = OrderStatus.PARTIALLY_CLOSED_INACTIVE
                # print('TP/SL CONTRACT PARTIALLY CLOSED INACTIVE')
            
            self.position._notify_change('standing_quantity', self.standing_quantity)
        
        elif self._tag == Tag.ORPHAN:
            # print('[BEFORE]', 'STANDING_QUANTITY:', self._standing_quantity, 'QUANTITY:', self.quantity)
            if clause:
                self._standing_quantity = 0
                
                if self.data['standing_quantity'] - quantity <= 0:
                    self.data['standing_quantity'] = 0
                    self.order_status = OrderStatus.CLOSED
                    self.position._notify_change('standing_quantity', self._standing_quantity)
                else:
                    self.order_status = OrderStatus.PARTIALLY_CLOSED_ACTIVE
                    self.data['standing_quantity'] -= quantity
                    # print('[TRUE][ORPHAN] ID:', self.data['order_id'], 'STANDING_QUANTITY:', self._standing_quantity, 'QUANTITY:', self.quantity)
            else:
                self._standing_quantity -= quantity
                self.data['standing_quantity'] -= quantity
                self.order_status = OrderStatus.PARTIALLY_CLOSED_ACTIVE
                # print('[FALSE][ORPHAN] ID:', self.data['order_id'], 'STANDING_QUANTITY:', self._standing_quantity, 'QUANTITY:', self.quantity)
                # if self.data['standing_quantity'] < 0:
                #     print('Standing quant < 0')
            # print('[AFTER]', 'STANDING_QUANTITY:', self._standing_quantity, 'QUANTITY:', self.quantity)

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
        return f"""Contract(side={self.side}, status={self.order_status}, standing_quantity={self.standing_quantity})"""

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
    def order_status(self) -> OrderStatus:
        return self._order_status
    
    @order_status.setter
    def order_status(self, value: OrderStatus) -> None:
        if value == self._order_status:
            return
        
        if value == OrderStatus.CLOSED:
            if self.position:
                if self.position.orphan_contract:
                    if self.position.orphan_contract != self and \
                        self.position.orphan_contract.order_status == OrderStatus.PARTIALLY_CLOSED_INACTIVE \
                    :
                        return
                    
        self._order_status = self.data['order_status'] = value
        
        if value == OrderStatus.CLOSED:
            self.data['closed_at'] = datetime.now()
        
        if self.position:
            self.position._notify_change('order_status', self.order_status)
        
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