from trading_engine.orderbook import OrderBook
from .commons import OrderStatus, OrderType
from .base_spot import BaseSpotOrder


class BidOrder(BaseSpotOrder):
    def __init__(self, data: dict, order_type: OrderType, **kwargs) -> None:
        super().__init__(data, order_type, **kwargs)

    def remove_from_orderbook(self, orderbook: OrderBook) -> None:
        try:
            price = self.data['limit_price'] or self.data['price']
            
            orderbook.bids[price].remove(self)
            
            if len(orderbook.bids[price]) == 0:
                del orderbook.bids[price]
        except (KeyError, ValueError):
            pass
    
    def append_to_orderbook(self, orderbook: OrderBook, price: float=None) -> None:
        if not price:
            price = \
                self.data['limit_price'] if self.data.get('limit_price', None) is not None\
                else self.data['price']
                
        orderbook.bids.setdefault(price, [])
        orderbook.bids[price].append(self)

    def alter_position(self, orderbook: OrderBook, price: float = None) -> None:
        self.remove_from_orderbook(orderbook)
        self.append_to_orderbook(orderbook, price)

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self):
        return f"BidOrder(order_id={self.data['order_id']})"

    @property
    def order_status(self):
        return self._order_status
    
    @order_status.setter
    def order_status(self, value: OrderStatus) -> None:
        self._order_status = self.data['order_status'] = value
        
        if value == OrderStatus.FILLED:
            self._open_price = self.data['filled_price']
            self.position_size = self.data['quantity'] * self.data['filled_price']
            