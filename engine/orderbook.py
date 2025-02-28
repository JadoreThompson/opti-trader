from typing import Literal, Optional
from engine.position import Position


class Orderbook:
    def __init__(self, instrument: str, price: float = 150) -> None:
        self.instrument = instrument
        self.bids: dict[float, list[Position]] = {}
        self.asks: dict[float, list[Position]] = {}
        self.bid_levels = self.bids.keys()
        self.ask_levels = self.asks.keys()
        self._price = price
        
    def append(self, order: dict, price: float) -> None:
        if order['side'] == 'buy':
            self.bids.setdefault(price, [])
            self.bids[price].append(Position(order))
            
        elif order['side'] == 'sell':
            self.asks.setdefault(price, [])
            self.asks[price].append(Position(order))
            
    def remove(self, position: Position):
        price = position.order['price'] or position.order['limit_price']
        
        if position.order['side'] == 'buy':
            try:
                self.bids[price].remove(position)
                if not self.bids[price]:
                    self.bids.pop(price)
                    
            except (ValueError, KeyError):
                pass
            
        elif position.order['side'] == 'sell':
            try:
                self.asks[price].remove(position)
                if not self.asks[price]:
                    self.asks.pop(price)
            except (ValueError, KeyError):
                pass
            
                
    def best_price(self, side: Literal['buy', 'sell'], price: float) -> Optional[float]:
        price_levels = self.bid_levels if side == 'sell' else self.ask_levels
        price_levels = list(price_levels)
        if not price_levels:
            return

        if price_levels[0] == None:
            return
        
        # print("[orderbook] Price Levels - ", price_levels, "Side - ", side)
        if side == 'sell':    
            cleaned_prices = {
                key: abs(price - key)
                for key in price_levels
                if key >= price
                and len(self.bids[key]) > 0
            }
            
        elif side == 'buy':
            cleaned_prices = {
                key: abs(price - key)
                for key in price_levels
                if key <= price
                and len(self.asks[key]) > 0
            }
            
        if cleaned_prices:
            return sorted(cleaned_prices.items(), key=lambda item: item[1])[0][0]
        
    def set_price(self, price: float) -> None:
        ...
        
    @property
    def price(self) -> float:
        return self._price
        
    def __getitem__(self, book: Literal['bids', 'asks']) -> dict:
        return self.bids if book == 'bids' else self.asks
        
    def __repr__(self) -> str:
        return f'Orderbook({self.instrument}, price={self.price}, bids={sum(len(self.bids[key]) for key in self.bids)}, asks={sum(len(self.asks[key]) for key in self.asks)})'
    