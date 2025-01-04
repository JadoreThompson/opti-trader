from enums import OrderStatus, Side
from ..order.contract import _FuturesContract

class _FuturesPosition:
    def __init__(
        self, 
        data: dict, 
        opening_contract: _FuturesContract,
    ) -> None:
        self.opening_contract = opening_contract
        self.closing_contract = None
        
        self._side = data['side']
        self._data = data
    
    def calculate_pnl(self, category: str, price: float=None) -> float:
        if category not in ['real', 'unreal']:
            raise ValueError("Category must be real or unreal")
        
        
        if category == 'unreal': 
            if not price:
                raise ValueError("Cannot calculate unrealised pnl without price param")
               
            price_change = ((price - self.opening_contract.price) / self.opening_contract.price) * 100
            
            if self._side == Side.SHORT:
                price_change *= -1
            
            
            pl = self.data[f'{category}_pnl'] = price_change * self.opening_contract.margin
            
                
        elif category == 'real':
            if self.closing_contract is None:
                raise ValueError("Cannot calculate realised pnl without a closing contract")

            price_change = ((self.closing_contract.price - self.opening_contract.price) / self.opening_contract.price)
            
            if self._side == Side.SHORT:
                price_change *= -1
                
            pl = self.data[f'{category}_pnl'] = price_change * (self.opening_contract.quantity * self.opening_contract.price)
        
        return pl

    @property
    def side(self) -> Side:
        return self._side

    @property
    def data(self) -> dict:
        return self._data


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
    
    op_pos = _FuturesPosition(op_data, op_contract)
    op_pos.closing_contract = cl_contract
    rpl = op_pos.calculate_pnl('real')
    