import json, asyncio
from datetime import datetime
from enums import _OrderType, OrderStatus

# Local
from .config import ASKS, BIDS

class _Order:
    """
    This class represents an order
    and some of  the properties to be used
    by the matching engine and order manager
    for retrieval and later computation
    """
    
    def __init__(self, data: dict, order_type: _OrderType, **kwargs) -> None:
        if isinstance(data['created_at'], str):
            data['created_at'] = datetime.strptime(data['created_at'], "%Y-%m-%d %H:%M:%S.%f")
        
        self.data = data
        self._quantity = data['quantity']
        self._standing_quantity = data['quantity']
        self._order_status = data['order_status']
        
        self._close_price = None
        self._open_price = kwargs.get('filled_price', None)
        self.order_type = order_type
        self._parent_order = kwargs.get('parent', None)
        
    @property
    def quantity(self):
        return self._quantity
        
    @property
    def close_price(self):
        return self._close_price
    
    @close_price.setter
    def close_price(self, value: float):
        self._close_price = value
    
    @property
    def open_price(self) -> float | None:
        return self._open_price

    @open_price.setter
    def open_price(self, value: float) -> None:
        self._open_price = value
    
    @property
    def standing_quantity(self):
        return self._standing_quantity
    
    @standing_quantity.setter
    def standing_quantity(self, value: int) -> None:
        self._standing_quantity = value
        self.data['standing_quantity'] = self._standing_quantity
    
    def reduce_standing_quantity(self, value: int):
        self._standing_quantity -= abs(value)
        self.data['standing_quantity'] = self._standing_quantity
        
    @property
    def order_status(self):
        return self._order_status

    @order_status.setter
    def order_status(self, value: OrderStatus):
        self._order_status = value
        
    def list(self) -> list:
        return [self.quantity, self.data]
        
    def __str__(self) -> str:
        return f"{self.data['order_id'][:5]} >> {self._order_status}"
        
    def __repr__(self):
        return f"{self.data['order_id'][:5]} >> {self._order_status}"
    
    def notify_order_close(self):
        if isinstance(self, AskOrder):
            self._parent_order.perform_order_close()


class BidOrder(_Order):
    def __init__(self, data: dict, order_type: _OrderType, **kwargs) -> None:
        super().__init__(data, order_type, **kwargs)
        
    @property
    def stop_loss(self) -> None | _Order:
        return self._stop_loss_order

    @property
    def take_profit(self) -> None | _Order:
        return self._take_profit_order

    def place_tp_sl(
        self, 
        ticker: str,
        take_profit_price: float = None, 
        stop_loss_price: float = None,
    ) -> None:
        """
        Places a copy of self.data and an _AskOrder object on the
        take_profit and stop_loss price level

        Args:
            ticker (str): 
            take_profit_price (float, optional): Defaults to None.
            stop_loss_price (float, optional): Defaults to None.
        """    
        try:
            BIDS[self.data['ticker']][self.data['filled_price']].remove(self)
        except ValueError:
            pass
        
        if take_profit_price:
            self._take_profit_order = AskOrder(self.data, _OrderType.TAKE_PROFIT_ORDER, parent=self)
            ASKS[ticker].setdefault(take_profit_price, [])
            ASKS[ticker][take_profit_price].append(self._take_profit_order)
        
        if stop_loss_price:
            self._stop_loss_order = AskOrder(self.data, _OrderType.STOP_LOSS_ORDER, parent=self)            
            ASKS[ticker].setdefault(stop_loss_price, [])
            ASKS[ticker][stop_loss_price].append(self._stop_loss_order)


    @property
    def order_status(self):
        return self._order_status
    
    @order_status.setter
    def order_status(self, value: OrderStatus) -> None:
        self._order_status = self.data['order_status'] = value
        
        if value == OrderStatus.FILLED:
            self._open_price = self.data['filled_price']            
            self.place_tp_sl(
                take_profit_price=self.data['take_profit'], 
                stop_loss_price=self.data['stop_loss'],
                ticker=self.data['ticker']
            )
            
    def perform_order_close(self):
        """
        Removes the stop loss and the take profit order
        from the ASKS array
        """        
        if self.data['take_profit']:
            try:
                ASKS[self.data['ticker']][self.data['take_profit']].remove(self._take_profit_order)
            except ValueError:
                pass
        
        if self.data['stop_loss']:
            try:
                ASKS[self.data['ticker']][self.data['stop_loss']].remove(self._stop_loss_order)
            except ValueError:
                pass
            

class AskOrder(_Order):
    def __init__(self, data: dict, order_type: _OrderType, **kwargs) -> None:
        super().__init__(data, order_type, **kwargs)

    @property
    def order_status(self):
        return self._order_status
    
    @order_status.setter
    def order_status(self, value: OrderStatus):
        self._order_status = self.data['order_status'] = value
        
        if value == OrderStatus.CLOSED:
            self.notify_order_close()
