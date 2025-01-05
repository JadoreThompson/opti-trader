import asyncio
import json
from pprint import pprint
import random
import logging 

from collections import defaultdict
from datetime import datetime, timedelta
from faker import Faker
from multiprocessing import Queue
from sqlalchemy import insert

# Local
from db_models import MarketData
from enums import PubSubCategory, UpdateScope
from exceptions import DoesNotExist
from models.models import APIOrder
from models.socket_models import (
    OrderUpdatePubSubMessage, 
    BasePubSubMessage
)
from utils.db import get_db_session
from .utils import publish_update_to_client
from .order.commons import OrderType, OrderStatus


Faker.seed(0)
fkr = Faker()

logger = logging.getLogger(__name__)

class OrderBook:
    _MAX_PRICE_SEARCH_ATTEMPTS = 5
    _PRICE_RATE_LIMIT = timedelta(seconds=2)

    def __init__(self, ticker: str, queue: Queue) -> None:
        self.queue = queue
        
        self._ticker = ticker
        self._bids: dict[float, list] = defaultdict(list)
        self._bid_levels = self._bids.keys()
        self._asks: dict[float, list] = defaultdict(list)
        self._ask_levels = self._asks.keys()
        self._price = None
        self._tracker: dict[str, dict[str, object]] = defaultdict(dict)
        self._dom = defaultdict(dict)
        self._blocked: bool = False
        self._lock = asyncio.Lock()
        self._last_price_performance = None

    async def set_price(self, price: float) -> None:
        async with self._lock:
            # print(len(self._bids[price]), 'bids')
            # print(len(self.asks[price]), 'asks')
            if price == self._price:
                return
            
            self._price = price
            
            tasks = [
                self._process_price(price),
                self._update_unrealised_pnl(price),
            ]
            
            for task in tasks:
                asyncio.get_running_loop().create_task(task)
            
            try:
                if datetime.now() - self._last_price_performance >= self._PRICE_RATE_LIMIT:        
                    self._last_price_performance = datetime.now()
                    asyncio.get_running_loop().create_task(self._update_dom(price))
            except TypeError:
                pass
        
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
        
    async def _update_unrealised_pnl(self, price: float) -> None:
        """Update unrealisd pnl for all orders and publish to the clients"""
        from .order.base_spot import BaseSpotOrder
        from .order.contract import _FuturesContract
        
        complete = False
        for _, v in self._tracker.copy().items():
            await asyncio.sleep(0.01)
            
            if not complete:
                continue
            try:
                if 'entry' not in v:
                    continue
                
                order = v['entry']
                
                if isinstance(order, BaseSpotOrder):        
                    if order.order_status in [OrderStatus.NOT_FILLED, OrderStatus.CLOSED]:
                        continue
                
                # Only here for testing
                if 'unrealised_pnl' not in order.data:
                    continue
                
                starting_upl = order.data['unrealised_pnl']
                
                pos_size = order.standing_quantity * order.data['filled_price']
                upl = (price / order.data['filled_price']) * (pos_size)
                order.data['unrealised_pnl'] += -1 * (pos_size - round(upl, 2))
                
                
                if not (order.data['unrealised_pnl'] == starting_upl):
                    await publish_update_to_client(**{
                        'channel': f'trades_{order.data['user_id']}',
                        'message': OrderUpdatePubSubMessage(
                            category=PubSubCategory.ORDER_UPDATE,
                            on=UpdateScope.EXISTING,
                            details=APIOrder(**order.data).model_dump()
                        ).model_dump()
                    })
                
            except Exception as e:
                logger.error('{} - {}'.format(type(e), str(e)))
    
    async def _update_dom(self, price: float) -> None:
        dom_size = 5
        dom = {'ticker': self._ticker}
        
        prices = [i for i in self._ask_levels if i > price][-1 * dom_size:]
        dom['asks'] = dict(
            zip(
                prices,
                [len(self._asks[price]) for price in prices]
            )
        )
        
        try:
            prices = [i for i in self._bid_levels if i < price][-5:]
            prices.sort(reverse=True)
        except Exception as e:
            logger.error('{} - {}'.format(type(e), str(e)))
            prices = []
            
        try:
            quantity = [len(self._bids[price]) for price in prices]
        except Exception as e:
            logger.error('{} - {}'.format(type(e), str(e)))
            quantity = []
            
        try:
            dom['bids'] = dict(
                zip(
                    prices,
                    quantity
                )
            )
        except Exception as e:
            logger.error('{} - {}'.format(type(e), str(e)))
            dom['bids'] = {}
        
        try:
            if dom != self._dom:
                self._dom = dom
                await publish_update_to_client(
                    **{
                        'channel': 'dom',
                        'message':
                            BasePubSubMessage(
                                category=PubSubCategory.DOM_UPDATE,
                                details=dom
                            ).model_dump()
                    }
                )
        except Exception as e:
            logger.error('{} - {}'.format(type(e), str(e)))

    def fetch(self, order_id: str):        
        """
        Returns the entry channel value for the order_id
        Args:
            order_id (str)

        Raises:
            DoesNotExist: doesn't exist within the tracker

        Returns:
            order: BaseSpotOrder | _FuturesContract
        """        
        try:
            return self._tracker[order_id]['entry']
        except KeyError:
            raise DoesNotExist(message=f"{order_id} doesn't exist in tracker")
    
    def track(self, **kwargs) -> None:
        """
        Appends a bid to tracking.

        Args:
            kwargs (dict): Arbitrary keyword arguments. Expected keys include:
                - order (BidOrder): The bid order to append.
                - contract (_FuturesContract): The contract to append
                - position (FuturesPosition): The position to track
                - channel (Optional[str]): Defaults to entry
        """   
        from .order.base_spot import BaseSpotOrder
        from .order.contract import _FuturesContract
        from .order.position import FuturesPosition
        
        channel = kwargs.get('channel', None) or 'entry'
        order = \
            kwargs.get('order', None) or \
            kwargs.get('contract', None) or \
            kwargs.get('position', None)
        
        if order is None:
            raise ValueError("An order (or equivalent) must be provided")
        
        if isinstance(order, _FuturesContract):
            id_key = order.contract_id
        elif isinstance(order, BaseSpotOrder):
            id_key = order.data['order_id']
        elif isinstance(order, FuturesPosition):
            id_key = order.contract.contract_id
        
        self._tracker[id_key][channel] = order
        
    def rtrack(self, **kwargs) -> None:
        """
        Removes order from tracking
        
        Args:
            kwargs: (dict)
                - order (BidOrder): The bid order to remove from tracking.
                - contract (_FuturesContract): The contract to remove from tracking.
                - position (FuturesPosition): The position to remove from tracking.
                - channel (str): The channel to remove from tracking
        """     
        from .order.base_spot import BaseSpotOrder
        from .order.contract import _FuturesContract
        from .order.position import FuturesPosition
        
        order = \
            kwargs.get('order', None) or \
            kwargs.get('contract', None) or \
            kwargs.get('position', None)
            
        channel: str = kwargs['channel']
        
        if isinstance(order, BaseSpotOrder):
            id_key = order.data['order_id']
        elif isinstance(order, _FuturesContract):
            id_key = order.contract_id
        elif isinstance(order, FuturesPosition):
            id_key = order.contract.contract_id
        
        if channel == 'all':
            for key in self._tracker[id_key].copy():
                try:
                    self._tracker[id_key][key].remove_from_orderbook(self, 'all')
                except ValueError:
                    pass
                del self._tracker[id_key][key]
        else:
            del self._tracker[id_key][channel]
        
    def alter_tp_sl(
        self, 
        order_id: str,
        new_tp_price: float=None, 
        new_sl_price: float=None,
    ) -> None:
        """Shifts the position of the Take Profit and Stop Loss order within the Orderbook"""
        if order_id not in self._tracker:
            return

        if new_sl_price:
            if (ex_order := self._tracker[order_id].get('stop_loss', None)):
                ex_order.alter_position(new_sl_price)
        
        if new_tp_price:
            if (ex_order := self._tracker[order_id].get('take_profit', None)):
                ex_order.alter_position(new_tp_price)
                
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
        if side not in ['ask', 'bid']:
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
                
            return sorted(cleaned_prices.items(), key=lambda item: item[1])[0][0]
        except ValueError:
            return None
        except IndexError:
            # Reversing if we can't find a level
            if count < self._MAX_PRICE_SEARCH_ATTEMPTS:
                count += 1
                return self.find_closest_price(
                    price, 
                    'ask' if side == 'bid' else 'bid', 
                    count
                )
            return None
        except Exception as e:
            logger.error('{} - {}'.format(type(e), str(e)))
                
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
                    'take_profit': None,
                    'stop_loss': None,
                    'filled_price': None
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
            
            self.track(order=order)
            order.append_to_orderbook(self)
            
            if i % divider == 0:
                order.data['filled_price'] = random.choice([i for i in tp if abs(bid_price - i) < 300])
                order.order_status = OrderStatus.FILLED
                order.remove_from_orderbook(self)
                
                if order.data.get('take_profit', None) is not None:
                    new_order = AskOrder(order.data, OrderType.TAKE_PROFIT_ORDER)
                    new_order.append_to_orderbook(self)
                    self.track(order=new_order, channel='take_profit')
                    
                if order.data.get('stop_loss', None) is not None:
                    new_order = AskOrder(order.data, OrderType.STOP_LOSS_ORDER)
                    new_order.append_to_orderbook(self)
                    self.track(order=new_order, channel='stop_loss')
        
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
        
    @property
    def dom(self) -> dict:
        return self._dom
    
### End of Class ###        
