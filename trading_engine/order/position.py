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
        
        self._entry_price: float = contract.price
        self._side: Side = contract.side
    
    def remove_from_orderbook(self, orderbook: OrderBook, category: str) -> None:
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
    
    def calculate_pnl(self, category: str, price: float=None, contract: _FuturesContract=None) -> float:
        if category not in ['real', 'unreal']:
            raise ValueError("Category must be real or unreal")
        
        if category == 'unreal': 
            if not price:
                raise ValueError('price must be provided')
            
            price_change = ((price - self.contract.price) / self.contract.price) * 100
            
            if self._side == Side.SHORT:
                price_change *= -1
            
            pnl = self.data[f'{category}_pnl'] = price_change * self.contract.margin
            print(f'side={self.contract.side}, ogp={self.contract.price}, np={price}', end=' ')    
        elif category == 'real':
            price_change = ((contract.price - self.contract.price) / self.contract.price)
            
            if self._side == Side.SHORT:
                price_change *= -1
                
            pnl = self.data[f'{category}_pnl'] = price_change * (self.contract.quantity * self.contract.price)
            print(f'side={self.contract.side}, ogp={self.contract.price}, np={contract.price}', end=' ')
        print(self, f'{category}ised_pnl={pnl}')
        
        return pnl
    
    def __repr__(self) -> str:
        return f'Position(cid={self.contract.contract_id})'

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
    