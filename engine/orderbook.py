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
        
    def append(self, order: dict):
        if order['side'] == 'buy':
            self.bids.setdefault(order['price'], [])
            self.bids[order['price']].append(Position(order))
            
        elif order['side'] == 'sell':
            self.asks.setdefault(order['price'], [])
            self.asks[order['price']].append(Position(order))
            
    def remove(self, position: Position):
        if position.order['side'] == 'buy':
            try:
                self.bids[position.order['price']].remove(position)
            except ValueError:
                pass
            
            if not self.bids[position.order['price']]:
                self.bids.pop(position.order['price'])
                
        elif position.order['side'] == 'sell':
            try:
                self.asks[position.order['price']].remove(position)
            except ValueError:
                pass
            
            if not self.asks[position.order['price']]:
                self.asks.pop(position.order['price'])
                
    def best_price(self, side: Literal['buy', 'sell'], price: float) -> Optional[float]:
        price_levels = self.bid_levels if side == 'sell' else self.ask_levels
        price_levels = list(price_levels)
        print("[orderbook] Price Levels - ", price_levels, "Side - ", side)
        if not price_levels:
            return

        if price_levels[0] == None:
            return
        
        if side == 'sell':    
            cleaned_prices = {
                key: abs(price - key)
                for key in price_levels
                if key >= price
                and len(self.asks[key]) > 0
            }
            
        elif side == 'buy':
            cleaned_prices = {
                key: abs(price - key)
                for key in price_levels
                if key <= price
                and len(self.bids[key]) > 0
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
    