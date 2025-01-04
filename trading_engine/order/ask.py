from trading_engine.orderbook import OrderBook
from .commons import OrderStatus, OrderType
from .base_spot import BaseSpotOrder


class AskOrder(BaseSpotOrder):
    def __init__(self, data: dict, order_type: OrderType, **kwargs) -> None:
        super().__init__(data, order_type, **kwargs)
        self._price_key: str = \
            'stop_loss' if self.order_type == OrderType.STOP_LOSS_ORDER \
            else 'take_profit'

    def remove_from_orderbook(self, orderbook: OrderBook) -> None:
        try:
            orderbook.asks[self.data[f'{self._price_key}']].remove(self)
            
            if len(orderbook.asks[self.data[f'{self._price_key}']]) == 0:
                del orderbook.asks[self.data[f'{self._price_key}']]
            
        except (KeyError, ValueError):
            pass

    def append_to_orderbook(self, orderbook: OrderBook, price: float=None) -> None:
        if not price:
            price = self.data[f"{self._price_key}"]
            
        orderbook.asks.setdefault(price, [])
        orderbook.asks[price].append(self)

    def alter_position(self, orderbook: OrderBook, price: float = None) -> None:
        self.remove_from_orderbook(orderbook)
        self.append_to_orderbook(orderbook, price)

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self):
        return f"AskOrder(order_id={self.data['order_id']})"
    