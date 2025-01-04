import multiprocessing
import redis

from typing import (
    Optional, 
    Tuple, 
    List, 
    Dict
)

from config import REDIS_HOST, ASYNC_REDIS_CONN_POOL
from enums import OrderStatus, PubSubCategory, Side, UpdateScope
from models.socket_models import BasePubSubMessage, FuturesContract, OrderUpdatePubSubMessage
from ..utils import publish_update_to_client
from ..order.contract import _FuturesContract
from ..orderbook import OrderBook

class FuturesEngine:
    def __init__(self, queue: multiprocessing.Queue) -> None:
        self.queue = queue
        self._order_books: dict[str, OrderBook] = {}
        self._redis = redis.asyncio.client.Redis(
            connection_pool=ASYNC_REDIS_CONN_POOL, 
            host=REDIS_HOST
        )
        
    async def _match_handler(self, data: dict) -> None: 
        contract: _FuturesContract = _FuturesContract(data)
        channel: str = f'trade_{data['user+id']}'
        
        if data['limit_price']:
            self._order_books[data['ticker']].append_bid(contract)
            return
        
        result = {
            Side.LONG: self._match_long,
            Side.SHORT: self._match_short
        }[contract.side](contract)
        
        await publish_update_to_client(**{
            0: {
                "channel": channel,
                'message': BasePubSubMessage(
                    category=PubSubCategory.ERROR,
                    message="Insufficient asks to fulfill bid order",
                ).model_dump()
            },
            
            1: {
                "channel": channel,
                'message': OrderUpdatePubSubMessage(
                    category=PubSubCategory.ORDER_UPDATE,
                    message="Order partially filled",
                    on=UpdateScope.NEW,
                    details=FuturesContract(**data).model_dump()
                ).model_dump()
            },
            
            2: {
                "channel": channel,
                'message': BasePubSubMessage(
                    category=PubSubCategory.SUCCESS,
                    message="Order successfully placed",
                    details=FuturesContract(**data).model_dump()
                ).model_dump()
            }
        }[result[0]])

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
                ex_contract.reduce_standing_quantity(ex_contract._standing_quantity)
                contract.reduce_standing_quantity(ex_contract._standing_quantity)
        
        for con in filled_cons:
            orderbook.remove()
    
    def _match_short(self, contract: _FuturesContract) -> Tuple[int, Optional[float]]:
        pass
        
    def _place_limit(self, contract: _FuturesContract):
        pass