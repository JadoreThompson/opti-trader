import logging

from enums import OrderStatus, Side
from trading_engine.orderbook import OrderBook
from ..order.base import Base
from ..order.contract import _FuturesContract

logger = logging.getLogger(__name__)

class FuturesPosition(Base):
    def __init__(
        self, 
        data: dict, 
        contract: _FuturesContract,
    ) -> None:
        super().__init__(data)
        
        self.contract: _FuturesContract = contract
        self.tp_contract: _FuturesContract = None
        self.sl_contract: _FuturesContract = None
        self.orphan_contract: _FuturesContract = None
        
        self._entry_price: float = contract.price
        self._side: Side = contract.side
    
    def remove_from_orderbook(self, orderbook: OrderBook, category: str) -> None:
        """
        Removes the contracts from orderbook
        
        Args:
            orderbook (OrderBook): 
            category (str):
                - all: Removes all associating contracts from the orderbook
                - entry: Removes the initial opening contracy from the orderbook
                - take_profit: Removes the take_profit contract from the orderbook
                - stop_loss: Removes the stop_loss contract from the orderbook

        Raises:
            ValueError: Invalid category
        """        
        if category not in ['entry', 'take_profit', 'stop_loss', 'all']:
            raise ValueError("Must pass a category in ['entry', 'take_profit', 'stop_loss', 'all']")
        
        try:
            if category == 'all':
                if self.tp_contract:
                    self.tp_contract.remove_from_orderbook(orderbook)
                
                if self.sl_contract:
                    self.sl_contract.remove_from_orderbook(orderbook)
                
                self.contract.remove_from_orderbook(orderbook)
                
            elif category == 'entry':
                self.contract.remove_from_orderbook(orderbook)
                
            elif category == 'stop_loss': 
                self.contract.remove_from_orderbook(orderbook)
                
            elif category == 'take_profit':
                self.contract.remove_from_orderbook(orderbook)
                
        except (KeyError, ValueError) as e:
            logger.error('{} - {}'.format(type(e), str(e)))  
    
    def alter_position(self, orderbook: OrderBook, tp_price: float=None, sl_price: float=None) -> None:
        """
        Alters the position by adding take profit and stop loss contracts to the orderbook
        
        Args:
            orderbook (OrderBook): 
            tp_price (float): 
            sl_price (float): 
        """
        if tp_price:
            try:
                if self.tp_contract is None:
                    self.tp_contract = _FuturesContract(self.data, tp_price, 'take_profit', self._side)
                else:
                    self.tp_contract.remove_from_orderbook(orderbook)
                
                self.tp_contract.append_to_orderbook(orderbook)
            except Exception as e:
                logger.error('Error whilst changing tp contract position {} - {}'.format(type(e), str(e)))
        
        if sl_price:
            try:
                if self.sl_contract is None:
                    self.sl_contract = _FuturesContract(self.data, sl_price, 'stop_loss', self._side)
                else:
                    self.sl_contract.remove_from_orderbook(orderbook)
                    
                self.sl_contract.append_to_orderbook(orderbook)
            except Exception as e:
                logger.error('Error whilst changing sl contract position {} - {}'.format(type(e), str(e)))
                
    def calculate_pnl(self, category: str, price: float=None, closing_contract: _FuturesContract=None) -> float:
        if category not in ['real', 'unreal']:
            raise ValueError("Category must be real or unreal")
        
        if category == 'unreal': 
            if not price:
                raise ValueError('price must be provided')
            
            price_change = ((price - self.contract.price) / self.contract.price) * 100
            
            if self._side == Side.SHORT:
                price_change *= -1
            
            pnl = self.data[f'{category}_pnl'] = price_change * self.contract.margin
            # print(f'side={self.contract.side}, ogp={self.contract.price}, np={price}', end=' ')    
        elif category == 'real':
            price_change = ((closing_contract.price - self.contract.price) / self.contract.price)
            
            if self._side == Side.SHORT:
                price_change *= -1
                
            pnl = self.data[f'{category}_pnl'] = price_change * (self.contract.quantity * self.contract.price)
            # print(f'side={self.contract.side}, ogp={self.contract.price}, np={contract.price}', end=' ')
        # print(self, f'{category}ised_pnl={pnl}')
        
        return pnl
    
    def _notify_change(self, field: str, value: any) -> None:
        """
        Notifies all contracts of a change in the position
        
        Args:
            field (str): Name of the attribute to change
            value (any): New value to set
        """        
        temp_field = f"_{field}" \
            if field == 'standing_quantity' \
                or field == 'order_status' \
            else field
        
        if self.sl_contract:
            if hasattr(self.sl_contract, temp_field):
                setattr(self.sl_contract, temp_field, value)
        
        if self.tp_contract:
            if hasattr(self.tp_contract, temp_field):
                setattr(self.tp_contract, temp_field, value)
        
        if self.orphan_contract:
            if hasattr(self.orphan_contract, temp_field):
                setattr(self.orphan_contract, temp_field, value)
        
        if field in self.contract.data:
            self.contract.data[field] = value
    
    def __repr__(self) -> str:
        return f'Position(cid={self.contract.contract_id}, side={self._side}, status={self.contract.order_status})'

    def __str__(self) -> str:
        return self.__repr__()

    @property
    def side(self) -> Side:
        return self._side

    @property
    def data(self) -> dict:
        return self._data

    @property
    def entry_price(self) -> float:
        return self._entry_price

    @entry_price.setter
    def entry_price(self, value: int) -> None:
        self._entry_price = self.contract.price = value

if __name__ == '__main__':
    op_data = {
        'side': Side.SHORT,
        'ticker': 'APPL',
        'quantity': 10,
        'standing_quantity': 10,
        'limit_price': 100,
        'status': OrderStatus.NOT_FILLED
    }
    op_contract = _FuturesContract(op_data)
    
    cl_data = op_data.copy()
    cl_data['side'] = Side.LONG
    cl_data['entry_price'] = 150
    cl_contract = _FuturesContract(cl_data)
    
    op_pos = FuturesPosition(op_data, op_contract)
    op_pos.closing_contract = cl_contract
    rpl = op_pos.calculate_pnl('real')
    