import asyncio
import datetime
import json
import multiprocessing
import redis
import logging
import queue

from typing import (
    Optional, 
    Tuple, 
    List, 
)

from config import REDIS_HOST, ASYNC_REDIS_CONN_POOL
from enums import (
    MarketType, 
    OrderStatus, 
    OrderType,
    PnlCategory, 
    PubSubCategory, 
    Side, 
    UpdateScope
)
from exceptions import DoesNotExist
from models.models import FuturesContractRead
from models.socket_models import BasePubSubMessage, OrderUpdatePubSubMessage
from ..enums import Tag
from ..orderbook import OrderBook
from ..utils import batch_update, publish_update_to_client
from ..order.contract import _FuturesContract
from ..order.position import FuturesPosition

logger = logging.getLogger(__name__)

class FuturesEngine:
    _MAX_MATCHING_ATTEMPTS = 20
    _MAX_PRICE_LEVEL_ATTEMPTS = 5
    
    def __init__(self, queue: multiprocessing.Queue) -> None:
        self.count = 0
        self.queue = queue
        self._order_books: dict[str, OrderBook] = {}
        self._redis = redis.asyncio.client.Redis(
            connection_pool=ASYNC_REDIS_CONN_POOL, 
            host=REDIS_HOST
        )
        self._handlers = {
            OrderType.MARKET: self._handle_match,
            OrderType.LIMIT: self._handle_match,
            OrderType.CLOSE: self._close,
            OrderType.MODIFY: self._modify_position,
        }
        
    async def start(
        self, 
        tickers: List[str], 
        price_queue: multiprocessing.Queue, 
        quantity: int=None, 
        divider: int=None
    ) -> None:
        """
        Listens to messages from the to_order_book channel
        and relays to the handler
        
        Args:
            kwargs (dict):
             - price_queue (multiprocessing.Queue): Used for the orderbook creation
        """
        for t in tickers:
            self._order_books[t] = OrderBook(t, price_queue)
            self._config_bid_ask(
                self._order_books[t], 
                quantity=quantity, 
                divider=divider
            )
        
        await self._listen()
    
    async def _listen(self) -> None:
        await asyncio.sleep(0.1)
        logger.info("Listening for messages")
        
        while True:
            try:
                message = self.queue.get_nowait()
                asyncio.create_task(self._route(message))
            except queue.Empty:
                pass
            except Exception as e:
                logger.error('{} - {}'.format(type(e), str(e)))
                
            await asyncio.sleep(0.01)
        
    async def _route(self, data: dict) -> None: 
        try:
            pub_params = {'channel': f"trades_{data['user_id']}"}
            pub_params.update(await self._handlers[data['type']](data=data, ))
            
            await publish_update_to_client(**pub_params)
        except Exception as e:
            logger.error('{} - {}'.format(type(e), str(e)), exc_info=True)  

    async def _handle_match(self, **kwargs) -> None:
        data = kwargs['data']
        orderbook: OrderBook = self._order_books[data['ticker']]
        position = FuturesPosition(
            data, 
            _FuturesContract(
                data, 
                data['price'] or data['limit_price'], 
                Tag.ENTRY,
                data['side'],
            )
        )
        position.contract.position = position
        orderbook.track(position=position, channel='position')

        if data['limit_price']:
            self._handle_limit(position, orderbook)
        else:    
            result = self._match(
                contract=position.contract,
                orderbook=orderbook,
            )
            
            print(result)
            
            try:
                if result[0] == 2:
                    print(position.contract.order_status)
                    await orderbook.set_price(result[1])
                    position.contract.data['filled_price'] = result[1]
                    self._place_tp_sl(position.contract, position, orderbook)
                else:
                    position.contract.append_to_orderbook(orderbook, )

            except Exception as e:
                logger.error('Error during handling of match result {} {} - {}'.format(result[0], type(e), str(e)))    
        
        await batch_update([position.contract.data])

        return {
            0: {
                'message': BasePubSubMessage(
                    category=PubSubCategory.ERROR,
                    message="Insufficient asks to fulfill bid order",
                ).model_dump()
            },
            
            1: {
                'message': OrderUpdatePubSubMessage(
                    category=PubSubCategory.ORDER_UPDATE,
                    message="Insufficient asks to fulfill bid order",
                    on=UpdateScope.NEW,
                    details=FuturesContractRead(**position.contract.data).model_dump()
                ).model_dump()
            },
            
            2: {
                'message': OrderUpdatePubSubMessage(
                    category=PubSubCategory.SUCCESS,
                    message="Order successfully placed",
                    on=UpdateScope.NEW,
                    details=FuturesContractRead(**position.contract.data).model_dump()
                ).model_dump()
            },
        }[result[0]]
        
    def _handle_limit(self, position: FuturesPosition, orderbook: OrderBook) -> None:
        position.contract.append_to_orderbook(orderbook,)
        self._place_tp_sl(position.contract, position, orderbook)

    async def _close(self, **kwargs) -> None:
        data = kwargs['data']
        orderbook = self._order_books[data['ticker']]
        
        try:
            position: FuturesPosition = orderbook.fetch(data['order_id'], 'position')
            position.orphan_contract = _FuturesContract(
                position.contract.data, 
                data['price'], 
                Tag.ORPHAN,
                Side(position.contract.side).invert(),
                orphan_quantity=data['quantity'],
            )
            position.orphan_contract.position = position
            result = self._match(
                contract=position.orphan_contract,
                orderbook=orderbook,
            )
            
            try:
                if result[0] == 2:
                    await orderbook.set_price(result[1])
                    if position.orphan_contract.order_status == OrderStatus.CLOSED:
                        position.orphan_contract.data['close_price'] = result[1]
                        position.calculate_pnl(PnlCategory.REALISED, result[1], tag=position.orphan_contract.data['order_id'])
                else:
                    position.orphan_contract.append_to_orderbook(orderbook)
                    
            except Exception as e:
                logger.error('Error during handling of close order {} - {}'.format(type(e), str(e)))
                
            await batch_update([position.contract.data])
            
            return {
                0: {
                    'message': BasePubSubMessage(
                        category=PubSubCategory.ERROR,
                        message="Insufficient liquidity to perform close",
                    ).model_dump()
                },
                
                1: {
                    'message': OrderUpdatePubSubMessage(
                        category=PubSubCategory.ORDER_UPDATE,
                        message="Close order partially filled",
                        on=UpdateScope.EXISTING,
                        details=FuturesContractRead(**position.contract.data).model_dump()
                    ).model_dump()
                },
                
                2: {
                    'message': OrderUpdatePubSubMessage(
                        category=PubSubCategory.ORDER_UPDATE,
                        message="Close order filled",
                        on=UpdateScope.EXISTING,
                        details=FuturesContractRead(**position.contract.data).model_dump()
                    ).model_dump()
                },
            }[result[0]]
            
        except DoesNotExist:
            return {
                'message': BasePubSubMessage(
                    category=PubSubCategory.ERROR,
                    message="Order not found",
                ).model_dump()
            }

    async def _modify_position(self, **kwargs) -> None:
        try:
            data = kwargs['data']
            position: FuturesPosition = self._order_books[data['ticker']].fetch(data['order_id'], 'position')
            position.alter_position(
                self._order_books[data['ticker']], 
                data['take_profit'], 
                data['stop_loss']
            )
            return {
                'message': BasePubSubMessage(
                    category=PubSubCategory.SUCCESS,
                    message="Order successfully modified",
                    on=UpdateScope.EXISTING,
                    details=FuturesContractRead(**position.contract.data).model_dump(),
                ).model_dump(),
            }
        except DoesNotExist:
            return {
                'message': BasePubSubMessage(
                    category=PubSubCategory.ERROR,
                    message="Order not found",
                ).model_dump()
            }
        
    def _match(self, **kwargs) -> Tuple[int, Optional[float]]:
        """Matches contract against opposite counterparties

        Args:
            kwargs:
                - contract (_FuturesContract): Contract to be matcher
                - orderbook (OrderBook): OrderBook to find orders in
        Returns:
            Tuple[int, Optional[float]]: _description_
        """        
        contract: _FuturesContract = kwargs['contract']
        book: str = \
            kwargs.get('book', None) or \
            ('bids' if contract.side == Side.SHORT else 'asks')    
        price = kwargs.get('price', None) or contract.data['price']
        attempts: int = kwargs.get('attempts', None) or 0 
        
        orderbook: OrderBook = self._order_books[contract.data['ticker']]
        price = orderbook.find_closest_price(price, book)
    
        if not price:
            return (0,)
        
        touched_cons: List[_FuturesContract] = []
        filled_cons: List[_FuturesContract] = []
        
        ex_contract: _FuturesContract
        for ex_contract in orderbook[book][price]:
            try:
                touched_cons.append(ex_contract)
                leftover_quantity = contract.standing_quantity - ex_contract.standing_quantity
                
                if leftover_quantity >= 0: 
                    filled_cons.append(ex_contract)
                    contract.reduce_standing_quantity(ex_contract.standing_quantity)
                    ex_contract.reduce_standing_quantity(ex_contract.standing_quantity)
                
                else:
                    ex_contract.reduce_standing_quantity(contract.standing_quantity)
                    contract.reduce_standing_quantity(contract.standing_quantity)
                
                if contract.standing_quantity == 0:
                    break
                if contract.standing_quantity < 0:
                    raise ValueError('Negative standing quantity')
            except Exception as e:
                logger.error(
                    'Error matching against a {} orders {} - {}'.format(book, type(e), str(e)),
                    exc_info=True
                )
        
        try:
            for ex_contract in filled_cons:
                if ex_contract.order_status == OrderStatus.CLOSED:
                    ex_contract.position.remove_from_orderbook(orderbook, 'all')
                    orderbook.rtrack(position=ex_contract.position, channel='all')
                    ex_contract.data['close_price'] = price
                    ex_contract.position.calculate_pnl(PnlCategory.REALISED, closing_contract=contract)
                else:
                    ex_contract.remove_from_orderbook(orderbook)
                    
                    if ex_contract.order_status == OrderStatus.FILLED:
                        ex_contract.data['filled_price'] = price
                        ex_contract._standing_quantity = ex_contract.data['standing_quantity'] = ex_contract.data['quantity']
                        self._place_tp_sl(ex_contract, ex_contract.position, orderbook)
            
            asyncio.create_task(batch_update([item.data for item in touched_cons]))
        except Exception as e:
            logger.error(
                'Error during handling of filled {} orders {} - {}'.format(book, type(e), str(e)),
                exc_info=True
            )
        
        if contract.standing_quantity == 0:
            return (2, price)

        if attempts < self._MAX_MATCHING_ATTEMPTS:
            attempts += 1
            return self._match(
                contract=contract,
                book=book,
                price=price,
                orderbook=orderbook,
                attempts=attempts,
            )

        return (1,)
    
    def _place_tp_sl(
        self, 
        contract: _FuturesContract, 
        position: FuturesPosition, 
        orderbook: OrderBook
    ) -> None:
        if contract.data['take_profit']:
            position.tp_contract = _FuturesContract(
                contract.data, 
                contract.data['take_profit'], 
                Tag.TAKE_PROFIT,
                contract.side.invert(),
            )
            position.tp_contract.append_to_orderbook(orderbook)
            position.tp_contract.position = position
        
        if contract.data['stop_loss']:
            position.sl_contract = _FuturesContract(
                contract.data, 
                contract.data['stop_loss'], 
                Tag.STOP_LOSS,
                contract.side.invert(),
            )
            position.sl_contract.append_to_orderbook(orderbook)
            position.sl_contract.position = position
    
    def _config_bid_ask(self, orderbook: OrderBook, quantity: int=10_000, divider: int=5) -> None:
        import random 
        from uuid import uuid4
        
        quantity = quantity or 10_000
        divider = divider or 5
        
        op_range = [i for i in range(300, 700, 10)]
        tp_range = [i for i in range(700, 1500, 10)]
        sl_range = [i for i in range(10, 300, 10)]
        
        for i in range(quantity):
            data = {
                'user_id': uuid4(),
                'order_id': uuid4(),
                'market_type': MarketType.FUTURES,
                'type': OrderType.MARKET,
                'ticker': 'BTC',
                'side': random.choice([Side.LONG, Side.SHORT]),
                'quantity': 10,
                'standing_quantity': 10,
                'filled_price': None,
                'limit_price': None,
                'price': random.choice([None, random.choice(op_range)]),
                'take_profit': random.choice([None, random.choice(tp_range)]),
                'stop_loss': random.choice([None, random.choice(sl_range)]),
                'order_status': OrderStatus.NOT_FILLED,
                'created_at': datetime.datetime.now(),
            }
            
            if data['price'] is None:
                data['limit_price'] = random.choice(op_range)
                data['type'] = OrderType.LIMIT
            
            position = FuturesPosition(
                data, 
                _FuturesContract(
                    data, 
                    data['price'] or data['limit_price'], 
                    Tag.ENTRY, 
                    data['side']
                )
            )
            
            position.contract.position = position
            orderbook.track(position=position, channel='position')
            
            if data['limit_price']:
                self._handle_limit(position, orderbook)
                continue
            
            if i % divider == 0:
                position.contract.remove_from_orderbook(orderbook)
                position.contract.order_status = OrderStatus.FILLED
                self._place_tp_sl(position.contract, position, orderbook)

### End of Class ###