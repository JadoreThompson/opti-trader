import asyncio
import random
import logging 

from collections import defaultdict, deque
from datetime import datetime
from faker import Faker
from multiprocessing import Queue
from sqlalchemy import insert

# Local
from db_models import MarketData
from exceptions import DoesNotExist
from utils.db import get_db_session
from .order.commons import OrderType, OrderStatus


Faker.seed(0)
fkr = Faker()

logger = logging.getLogger(__name__)

class OrderBook:
    _MAX_PRICE_SEARCH_ATTEMPTS = 5

    _bids: dict[float, list] = defaultdict(list)
    _bid_levels = _bids.keys()
    _asks: dict[float, list] = defaultdict(list)
    _ask_levels = _asks.keys()
    
    _price = None
    _orders: dict[str, dict[str, "BidOrder | AskOrder"]] = defaultdict(dict)

    def __init__(self, ticker: str, queue: Queue) -> None:
        self._ticker = ticker
        self.queue = queue
    
    @property
    def ticker(self) -> str:
        return self._ticker    
    
    @property
    def asks(self):
        return self._asks
    
    @property
    def ask_levels(self):
        return self._ask_levels
    
    @property
    def bids(self):
        return self._bids

    @property
    def bid_levels(self):
        return self._bid_levels
    
    @property
    def price(self) -> float:
        return self._price
    
    @price.setter
    def price(self, price: float) -> None:
        if price == self._price:
            return
        
        self._price = price
        asyncio.get_running_loop().create_task(self._process_price(price))
    
    async def _process_price(self, price: float) -> None:
        """Persist price in DB and push to the client manager"""
        await self._persist_price_(price)
        try:
            self.queue.put_nowait((self.ticker, price))
        except Exception as e:
            logger.error(f'{type(e)} - {str(e)}')
    
    async def _persist_price_(self, price: float) -> None:
        try:
            async with get_db_session() as session:
                await session.execute(
                    insert(MarketData)
                    .values(
                        ticker=self.ticker,
                        date=int(datetime.now().timestamp()),
                        price=price
                    )
                )
                await session.commit()
        except Exception as e:
            logger.error('{} - {}'.format(type(e), str(e)))
        
    
    def fetch(self, order_id: str) -> "BidOrder":        
        try:
            return self._orders[order_id]['entry']
        except KeyError:
            raise DoesNotExist(order_id)
        
    def append_bid(self, order: "BidOrder", price: float=None, to_book=True) -> None:
        try:
            if not price:
                price = order.data['filled_price'] if order.data.get('filled_price', None) is not None\
                    else order.data['price']
            
            if to_book:
                self.bids.setdefault(price, [])
                self.bids[price].append(order)
                
            self._orders[order.data['order_id']]['entry'] = order
        except Exception as e:
            logger.error('{} - {}'.format(type(e), str(e)))
        
    def append_ask(self, price: float, order: "AskOrder") -> None:
        if order.data['order_id'] not in self._orders:
            raise DoesNotExist(message="You must append bid first")
        
        # self.asks.setdefault(price, [])
        self.asks[price].append(order)
        
        if order.order_type == OrderType.STOP_LOSS_ORDER:
            self._orders[order.data['order_id']]['stop_loss'] = order
        elif order.order_type == OrderType.TAKE_PROFIT_ORDER:
            self._orders[order.data['order_id']]['take_profit'] = order
        
    def remove_order(self, order: "AskOrder | BidOrder", tracking=False) -> None:
        """Removes order from orderbook and optionally from tracking"""
        from .order.ask import AskOrder
        
        order_id: str = order.data['order_id']
        
        if order_id not in self._orders:
            return
        
        key = None
        order = None
        
        try:
            if isinstance(order, AskOrder):
                key = 'stop_loss' if order.order_type == OrderType.STOP_LOSS_ORDER else 'take_profit'
                order = self._orders[order_id][key]
                
                try:
                    self.asks[order.data[f'{key}_price']].remove(order)
                    if len(self.asks[order.data[f'{key}_price']]) == 0:
                        del self.asks[order.data[f'{key}_price']]
                except ValueError:
                    pass
            else:
                key = 'entry'
                order = self._orders[order_id][key]
                
                try:
                    self.bids[order.data['price']].remove(order)
                except ValueError:
                    pass
                try:
                    if len(self.bids[order.data['price']]) == 0:
                        del self.bids[order.data['price']]
                except KeyError:
                    pass
                
            
            if tracking:
                del self._orders[order_id][key]
        except KeyError:
            pass
    
    def remove_related_orders(self, order_id: str) -> None:
        """Removes the order_id and it's components from their place in the orderbook and tracking"""
        if order_id not in self._orders:
            return
        
        try:
            order = self._orders[order_id]['entry']
            price = order.data['filled_price'] if order.data.get('filled_price', None) is not None \
                else order.data['price']
            self.bids[price].remove(order)

            if len(self.bids[price]) == 0:
                del self.bids[price]
        except (ValueError, KeyError):
            pass
            
        for key in ['stop_loss', 'take_profit']:    
            if key not in self._orders[order_id]:
                continue

            try:
                order = self._orders[order_id][key]
                self.asks[order.data[key]].remove(order)
                if len(self.asks[order.data[key]]) == 0:
                        del self.asks[order.data[key]]
            except ValueError:
                pass
            except KeyError as e:
                logger.error('{} - {}'.format(type(e), str(e)))
        
        del self._orders[order_id]
        
    def alter_tp_sl(
        self, 
        order_id: str,
        new_take_profit_price: float=None, 
        new_stop_loss_price: float=None,
    ) -> None:
        """Shifts the position of the Take Profit and Stop Loss order within the Orderbook"""
        if order_id not in self._orders:
            raise DoesNotExist(order_id)
        
        if new_take_profit_price:
            existing_order = self._orders[order_id].get('take_profit', None)
            if existing_order:
                self.asks[existing_order.data['take_profit']].remove(existing_order)
                self.asks.setdefault(new_take_profit_price, [])
                self.asks[new_take_profit_price].append(existing_order)
                existing_order.data['take_profit'] = new_take_profit_price
        
        if new_stop_loss_price:
            existing_order = self._orders[order_id].get('stop_loss', None)
            if existing_order:
                self.asks[existing_order.data['stop_loss']].remove(existing_order)
                self.asks.setdefault(new_stop_loss_price, [])
                self.asks[new_stop_loss_price].append(existing_order)
                existing_order.data['stop_loss'] = new_stop_loss_price
    
    def find_closest_price(
        self,
        price: float,
        side: str,
        count: int=0
    ) -> float:
        """
        Finds the closest ask or bid price level to the param price within the book

        Args:
            price (float)
            side (str): ask or bid

        Returns:
            float: Closest price level to the original price passed in param
            None: No price could be found
        """         
        if side != 'ask' and side != 'bid':
            raise ValueError('Book must be either ask or bid')

        price_levels = self.ask_levels if side == 'ask' else self.bid_levels
        
        try:
            if side == 'ask':    
                cleaned_prices = {
                    key: abs(price - key)
                    for key in list(price_levels)
                    if key >= price
                    and len(self.asks[key]) > 0
                }
                
            elif side == 'bid':
                cleaned_prices = {
                    key: abs(price - key)
                    for key in list(price_levels)
                    if key <= price
                    and len(self.bids[key]) > 0
                }
                
            result = sorted(cleaned_prices.items(), key=lambda item: item[1])[0][0]
            return result
        except ValueError:
            return None
        except IndexError:
            if count < self._MAX_PRICE_SEARCH_ATTEMPTS:
                count += 1
                return self.find_closest_price(
                    price, 
                    'ask' if side == 'bid' else 'bid', 
                    count
                )
            return None
                
    def _configure_bid_asks(self, quantity: int=1000, divider: int=5) -> None:
        """
        Populate the orderbook with artificial orders
        
        Args:
            quantity (int): Total quantity of orders being pushed to orderbook
            divider (int): Ratio of bids to asks. divider=5 results in 40 ask orders with quantity=200
        """
        from .order.bid import BidOrder
        from .order.ask import AskOrder
        
        tp = [i for i in range(100, 1000, 5)]
        sl = [i for i in range(20, 1000, 5)]
        
        for i in range(quantity):
            order = BidOrder(
                {
                    'order_id': fkr.pystr(), 
                    'quantity': random.randint(1, 5), 
                    'order_status': random.choice([OrderStatus.NOT_FILLED, OrderStatus.PARTIALLY_FILLED]), 
                    'created_at': datetime.now(),
                    'ticker': 'APPL',
                },
                # random.choice([OrderType.LIMIT_ORDER, OrderType.MARKET_ORDER])
                OrderType.MARKET_ORDER
            )
            
            bid_price = random.choice([i for i in range(20, 1000, 5)])
            if order.order_type == OrderType.LIMIT_ORDER:
                order.data['limit_price'] = bid_price
            else:                
                order.data['price'] = bid_price

            order.data['take_profit'] = random.choice(tp)
            order.data['stop_loss'] = random.choice(sl)
            
            self.append_bid(order, bid_price, False)
            
            if i % divider == 0:
                order.data['filled_price'] = random.choice([i for i in tp if abs(bid_price - i) < 300])
                order.order_status = OrderStatus.FILLED
                
                self.remove_order(order, True)
                
                if order.data.get('take_profit', None) is not None:
                    self.append_ask(order.data['take_profit'], AskOrder(order.data, OrderType.TAKE_PROFIT_ORDER))
                if order.data.get('stop_loss', None) is not None:
                    self.append_ask(order.data['stop_loss'], AskOrder(order.data, OrderType.STOP_LOSS_ORDER))
        
### End of Class ###        
