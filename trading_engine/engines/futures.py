import asyncio
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
from enums import OrderStatus, OrderType, Side
from ..order.position import FuturesPosition
from ..utils import publish_update_to_client
from ..order.contract import _FuturesContract
from ..orderbook import OrderBook

logger = logging.getLogger(__name__)

class FuturesEngine:
    def __init__(self, queue: multiprocessing.Queue) -> None:
        self.queue = queue
        self._order_books: dict[str, OrderBook] = {}
        self._redis = redis.asyncio.client.Redis(
            connection_pool=ASYNC_REDIS_CONN_POOL, 
            host=REDIS_HOST
        )
        self._handlers = {
            OrderType.MARKET: self._create_contract,
            OrderType.LIMIT: self._create_contract,
            OrderType.CLOSE: self._close_contract,
            OrderType.MODIFY: self._modify_contract,
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
                if isinstance(message, dict):
                    asyncio.create_task(self._route(message))
            except queue.Empty:
                pass
            except Exception as e:
                logger.error('{} - {}'.format(type(e), str(e)))
                
            await asyncio.sleep(0.01)
        
    async def _route(self, data: dict) -> None: 
        try:
            await self._handlers[data['type']](
                data=data, 
                channel=f"trades_{data['user_id']}"
            )
        except Exception as e:
            logger.error('{} - {}'.format(type(e), str(e)))
    
    async def _create_contract(self, data: dict, channel: str) -> None:
        contract: _FuturesContract = _FuturesContract(
            data, 
            data['entry_price'] or data['limit_price'], 
            side=data['side'],
        )
        orderbook: OrderBook = self._order_books[data['ticker']]
        
        if data['limit_price']:
            result = self._handle_limit(data, contract, orderbook)
            return
        
        result = {
            Side.LONG: self._match_long,
            Side.SHORT: self._match_short
        }[contract.side](contract)

        if result[0] == 2:
            await orderbook.set_price(result[1])
            contract.status = OrderStatus.FILLED
            contract.data['filled_price'] = result[1]
            
            pos = FuturesPosition(data, contract)
            orderbook.track(position=pos)
            self._place_tp_sl(contract, pos, orderbook)
        
        else:
            contract.append_to_orderbook(orderbook)

        # await publish_update_to_client(**{
        #     0: {
        #         "channel": channel,
        #         'message': BasePubSubMessage(
        #             category=PubSubCategory.ERROR,
        #             message="Insufficient asks to fulfill bid order",
        #         ).model_dump()
        #     },
            
        #     1: {
        #         "channel": channel,
        #         'message': OrderUpdatePubSubMessage(
        #             category=PubSubCategory.ORDER_UPDATE,
        #             message="Insufficient asks to fulfill bid order",
        #             on=UpdateScope.NEW,
        #             details=FuturesContract(**data).model_dump()
        #         ).model_dump()
        #     },
            
        #     2: {
        #         "channel": channel,
        #         'message': BasePubSubMessage(
        #             category=PubSubCategory.SUCCESS,
        #             message="Order successfully placed",
        #             details=FuturesContract(**data).model_dump()
        #         ).model_dump()
        #     }
        # }[result[0]])
        
    def _handle_limit(self, data: dict, contract: _FuturesContract, orderbook: OrderBook) -> None:
        contract.append_to_orderbook(orderbook, data['limit_price'])
        pos = FuturesPosition(data, contract)
        orderbook.track(position=pos)
        self._place_tp_sl(contract, pos, orderbook)

    async def _close_contract(self, **kwargs) -> None:
        pass

    async def _modify_contract(self, **kwargs) -> None:
        pass

    def _match_long(self, contract: _FuturesContract) -> Tuple[int, Optional[float]]:
        """Matches against the contracts within the ask book"""
        # Current Implementation: FIFO
        
        orderbook: OrderBook = self._order_books[contract.data['ticker']]
        ask_price = orderbook.find_closest_price(contract.data['entry_price'], 'ask')
        
        if not ask_price:
            return (0,)
        
        touched_cons: List[_FuturesContract] = []
        filled_cons: List[_FuturesContract] = []
        
        ex_contract: _FuturesContract
        for ex_contract in orderbook.asks[ask_price]:
            touched_cons.append(ex_contract)
            leftover_quantity = contract._standing_quantity - ex_contract._standing_quantity
            
            if leftover_quantity >= 0: 
                filled_cons.append(ex_contract)
                contract.reduce_standing_quantity(ex_contract._standing_quantity)
                ex_contract.reduce_standing_quantity(ex_contract._standing_quantity)
            
            else:
                ex_contract.reduce_standing_quantity(contract.standing_quantity)
                contract.reduce_standing_quantity(contract.standing_quantity)

            if contract.standing_quantity == 0:
                break
            
        for ex_contract in filled_cons:
            if ex_contract.tag in ['stop_loss', 'take_profit']:
                orderbook.rtrack(position=ex_contract.position, channel='all')
                ex_contract.position.remove_from_orderbook(orderbook, 'all')
                ex_contract.position.calculate_pnl('real', contract=contract)
            else:
                ex_contract.remove_from_orderbook(orderbook)
                new_pos = FuturesPosition(ex_contract.data, ex_contract)
                self._place_tp_sl(ex_contract, new_pos, orderbook)
                orderbook.track(position=new_pos)
        
        if contract.standing_quantity == 0:
            return (2, ask_price)

        return (1,)
    
    def _match_short(self, contract: _FuturesContract) -> Tuple[int, Optional[float]]:
        orderbook: OrderBook = self._order_books[contract.data['ticker']]
        bid_price = orderbook.find_closest_price(contract.data['entry_price'], 'bid')
        
        if not bid_price:
            return (0,)
        
        touched_cons: List[_FuturesContract] = []
        filled_cons: List[_FuturesContract] = []
        
        ex_contract: _FuturesContract
        for ex_contract in orderbook.bids[bid_price]:
            touched_cons.append(ex_contract)
            leftover_quantity = contract._standing_quantity - ex_contract._standing_quantity
            
            if leftover_quantity >= 0: 
                filled_cons.append(ex_contract)
                contract.reduce_standing_quantity(ex_contract._standing_quantity)
                ex_contract.reduce_standing_quantity(ex_contract._standing_quantity)
            
            else:
                ex_contract.reduce_standing_quantity(contract.standing_quantity)
                contract.reduce_standing_quantity(ex_contract.standing_quantity)
            
            if contract.standing_quantity == 0:
                break
        
        for ex_contract in filled_cons:
            if ex_contract.tag in ['stop_loss', 'take_profit']:
                orderbook.rtrack(position=ex_contract.position, channel='all')
                ex_contract.position.remove_from_orderbook(orderbook, 'all')
                ex_contract.position.calculate_pnl('real', contract=contract)
            else:
                ex_contract.remove_from_orderbook(orderbook)
                new_pos = FuturesPosition(ex_contract.data, ex_contract)
                self._place_tp_sl(ex_contract, new_pos, orderbook)
                orderbook.track(position=new_pos,)
        
        if contract.standing_quantity == 0:
            return (2, bid_price)

        return (1,)
    
    def _place_tp_sl(
        self, 
        contract: _FuturesContract, 
        position: FuturesPosition, 
        orderbook: OrderBook
    ) -> None:
        if contract.data['take_profit']:
            _contract: _FuturesContract = _FuturesContract(
                contract.data, 
                contract.data['take_profit'], 
                'take_profit',
                contract.side.invert(),
            )
            _contract.append_to_orderbook(orderbook)
            _contract.position = position
            position.tp_contract = _contract
        
        if contract.data['stop_loss']:
            _contract: _FuturesContract = _FuturesContract(
                contract.data, 
                contract.data['stop_loss'], 
                'stop_loss',
                contract.side.invert(),
            )
            _contract.append_to_orderbook(orderbook)
            _contract.position = position
            position.sl_contract = _contract
    
    def _config_bid_ask(self, orderbook: OrderBook, quantity: int=10_000, divider: int=5) -> None:
        import random 
        from uuid import uuid4
        
        quantity = quantity or 10_000
        divider = divider or 5
        
        op_range = [i for i in range(60, 200, 10)]
        tp_range = [i for i in range(200, 310, 10)]
        sl_range = [i for i in range(0, 60, 10)]
        
        for i in range(quantity):
            data = {
                'user_id': uuid4(),
                'ticker': 'BTC',
                'side': random.choice([Side.LONG, Side.SHORT]),
                'quantity': 10,
                'standing_quantity': 10,
                'filled_price': None,
                'limit_price': None,
                'entry_price': random.choice([None, random.choice(op_range)]),
                'take_profit': random.choice([None, random.choice(tp_range)]),
                'stop_loss': random.choice([None, random.choice(sl_range)]),
                'status': OrderStatus.NOT_FILLED,
            }
            
            if data['entry_price'] is None:
                data['limit_price'] = random.choice(op_range)
            
            contract = _FuturesContract(
                data, 
                data['limit_price'] or data['entry_price'], 
                side=data['side'],
            )
            
            contract.append_to_orderbook(orderbook)
            
            if i % divider == 0:
                contract.remove_from_orderbook(orderbook)
                contract.status = OrderStatus.FILLED
                
                new_pos = FuturesPosition(data, contract)
                
                self._place_tp_sl(contract, new_pos, orderbook)
                orderbook.track(position=new_pos)

### End of Class ###