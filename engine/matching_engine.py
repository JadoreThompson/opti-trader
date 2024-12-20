import asyncio 
import json
import time 
import redis 
import logging
import queue

from collections import deque
from datetime import datetime
from multiprocessing import Queue
from typing import Optional
from uuid import UUID


# Local
from config import REDIS_HOST, REDIS_CONN_POOL
from enums import ConsumerMessageStatus, OrderType, OrderStatus
from models.models import APIOrder
from exceptions import DoesNotExist

from .enums import OrderType as _OrderType
from .orderbook import OrderBook
from .utils import batch_update
from .order.bid import BidOrder
from .order.ask import AskOrder


logger = logging.getLogger(__name__)


class MatchingEngine:
    _MAX_MATCHING_ATTEMPTS = 20
    _MAX_PRICE_LEVEL_ATTEMPTS = 5
    _order_book: dict[str, OrderBook] = {}
    _redis = redis.asyncio.client.Redis(connection_pool=REDIS_CONN_POOL, host=REDIS_HOST)
    _current_price = deque()

    def __init__(self, queue=None) -> None:
        self.order_queue = queue
        self._handlers: dict = {
            OrderType.MARKET: self._handle_market_order,
            OrderType.CLOSE: self._handle_close_order,
            OrderType.LIMIT: self._handle_limit_order,
            OrderType.MODIFY: self._handle_modify_order,
        }

    async def main(self, price_queue: Queue) -> None:
        """
        Listens to messages from the to_order_book channel
        and relays to the handler
        """
        try: 
            self._order_book.setdefault('APPL', OrderBook('APPL', price_queue))
            self._order_book['APPL']._configure_bid_asks(10_000, 2)

            logger.info('Initialising Engine')
            await self._listen()
        except Exception as e:
            logger.error(f'{type(e)} - {str(e)}')
        
    async def _listen(self) -> None:
        """
        Perpetually queries the queue for any incoming orders
        """    
        await asyncio.sleep(0.1)        
        logger.info('Listening for messages')
        
        while True:
            try:
                message = self.order_queue.get_nowait()
                if isinstance(message, dict):
                    asyncio.create_task(self._handle_incoming_message(message))
            except queue.Empty:
                pass
            
            await asyncio.sleep(0.001)
        
    async def _handle_incoming_message(self, message: dict) -> None:        
        try:
            await self._handlers[message['type']](
                data=message, 
                channel=f"trades_{message['user_id']}"
            )
        except Exception as e:
            logger.error(f'{message['type']} - {type(e)} - {str(e)}')

    async def _publish_update_to_client(self, channel: str, message: str | dict) -> None:
        """
        Publishes message to Redis channel

        Args:
            channel (str):
            message (str): 
        """        
        try:
            if isinstance(message, dict):
                message = json.dumps(message)
            
            if isinstance(message, str):
                await self._redis.publish(channel=channel, message=message)
        except Exception as e:
            logger.error(str(e))

    async def _handle_market_order(self, data: dict, channel: str) -> None:
        """
        Central point for matching bid against asks
        as well as user notifications

        Args:
            data (dict).
            channel (str).
        """
        await asyncio.sleep(0.01)
        orderbook = self._order_book[data['ticker']]
        
        try:       
            order = BidOrder(data, _OrderType.MARKET_ORDER)
            orderbook.append_bid(order, to_book=False)    
            start = time.time()
            result: tuple = self.match_bid_order(
                order=order, 
                ticker=order.data['ticker'], 
                orderbook=orderbook
            )
            
            async def not_filled(**kwargs):
                return
            
            async def partial_fill(**kwargs):
                data: dict = kwargs['data']
                order: BidOrder = kwargs['order']
                orderbook: OrderBook = kwargs['orderbook']
                
                try:
                    order.order_status = OrderStatus.PARTIALLY_FILLED
                    orderbook.append_bid(order, data['price'])
                    await batch_update([data])
                except Exception as e:
                    logger.error(f'handle market order -> {str(e)}')
        
            async def filled(**kwargs):
                data: dict = kwargs['data']
                order: BidOrder = kwargs['order']
                result: tuple = kwargs['result']
                
                try:
                    data["filled_price"] = result[1]
                    order.order_status = OrderStatus.FILLED
                    order.standing_quantity = data['quantity']
                    if order.data['take_profit'] is not None:
                        new_order = AskOrder(order.data, _OrderType.TAKE_PROFIT_ORDER)
                        orderbook.append_ask(order.data['take_profit'], new_order)
                    if order.data['stop_loss'] is not None:
                        new_order = AskOrder(order.data, _OrderType.STOP_LOSS_ORDER)
                        orderbook.append_ask(order.data['stop_loss'], new_order)
                    
                    
                    asyncio.create_task(batch_update([data]))
                    await asyncio.sleep(0)

                    orderbook.price = result[1]
                except Exception as e:
                    logger.error(f'{type(e)} - {str(e)}')
        
            await {0: not_filled, 1: partial_fill, 2: filled}[result[0]]\
                (result=result, data=data, order=order, orderbook=orderbook)
     
            orderbook.append_bid(order)
        
            await self._publish_update_to_client(**{
                    0: {
                        "channel": channel,
                        "message": {
                            'status': ConsumerMessageStatus.ERROR,
                            'internal': OrderType.MARKET,
                            'message': 'Isufficient asks to fiullfill bid order',
                            'details': { 'order_id': data['order_id'] }
                        }
                    },
                    1: {
                        "channel": channel,
                        "message": json.dumps({
                            "status": ConsumerMessageStatus.UPDATE, 
                            'internal': OrderType.MARKET,
                            "message": "Order partially filled",
                            "details": {
                                k: (str(v) if isinstance(v, (datetime, UUID)) else v) 
                                for k, v in APIOrder(**data).model_dump().items()
                            }
                        })
                    },
                    2: {
                        "channel": channel,
                        "message": json.dumps({
                            "status": ConsumerMessageStatus.SUCCESS,
                            'internal': OrderType.MARKET,
                            "message": "Order successfully placed",
                            "details": {
                                k: (str(v) if isinstance(v, (datetime, UUID)) else v) 
                                for k, v in APIOrder(**data).model_dump().items()
                            }
                        })
                    }
                }[result[0]])
        except Exception as e:
            logger.error(f'{type(e)} - {str(e)}')
    
    def match_bid_order(
        self, 
        ticker: str,
        orderbook: OrderBook,
        order: BidOrder=None,
        bid_price: float=None,
        attempts: float=0,
    ) -> tuple:
        """
        Matches quantity from main
        
        Args:
            ticker (str)
            orderbook (OrderBook)
            order (BidOrder): Defaults to None

        Returns:
            (0,): Order couldn't be filled due to insufficient asks
            (1,): Order was partially filled
            (2, ask_price): Order was successfully filled
        """
        try:
            if not bid_price:
                bid_price = order.data["price"]
            
            ask_price = orderbook.find_closest_price(bid_price, 'ask')
            if ask_price is None:
                return (0,)

            closed_orders = []
            touched_orders = []            
            
            for ex_order in orderbook.asks[ask_price]:
                touched_orders.append(ex_order)
                leftover_quant = order.standing_quantity - ex_order.standing_quantity
                
                if leftover_quant >= 0:
                    order.reduce_standing_quantity(ex_order.standing_quantity)
                    closed_orders.append(ex_order)
                    ex_order.standing_quantity = 0
                    ex_order.data['close_price'] = ask_price
                    ex_order.data['closed_at'] = datetime.now()

                else:
                    ex_order.reduce_standing_quantity(order.standing_quantity)
                    order.standing_quantity = 0
                    
                    if ex_order.order_type in [_OrderType.TAKE_PROFIT_ORDER, _OrderType.STOP_LOSS_ORDER]:
                        ex_order.order_status = OrderStatus.PARTIALLY_CLOSED_INACTIVE
                    else:
                        # Order must be part of an unplanned close request from user
                        ex_order.order_status = OrderStatus.PARTIALLY_CLOSED_ACTIVE
                        
                if order.standing_quantity == 0:
                    break
            
            for item in closed_orders:
                try:
                    item.order_status = OrderStatus.CLOSED
                    orderbook.remove_related_orders(item.data['order_id'])
                except ValueError:
                    pass
            
            asyncio.create_task(batch_update([item.data for item in touched_orders]))    
            if order.standing_quantity == 0:
                return (2, ask_price)

            if attempts < self._MAX_MATCHING_ATTEMPTS:
                attempts += 1
                return self.match_bid_order(
                    ticker=ticker,
                    order=order,
                    orderbook=orderbook,
                    bid_price=ask_price,
                    attempts=attempts
                )

            return (1,)
        except Exception as e:
            import traceback
            logger.error(f'{traceback.extract_tb(e.__traceback__)[-1].line} {type(e)} - {str(e)}')
    
    async def _handle_limit_order(self, channel: str, data: dict) -> None:
        """
        Places a bid order on the desired price
        for the limit order along with placing the TP and SL of the order

        Args:
            order (dict)
        """        
        
        try:
            self._order_book[data['ticker']].append_bid(
                BidOrder(data, _OrderType.LIMIT_ORDER), 
                data['limit_price']
            )
            
            await self._publish_update_to_client(
                channel=channel,
                message=json.dumps({
                    'status': 'success',
                    'internal': OrderType.LIMIT,
                    'message': 'Limit order created successfully',
                    'order_id': data['order_id'],
                    "details": {
                        k: (str(v) if isinstance(v, (datetime, UUID)) else v) 
                        for k, v in APIOrder(**data).model_dump().items()
                    }
                })
            )
        except Exception as e:
            logger.error(f'{type(e)} - {str(e)}')
    
    async def _handle_close_order(self, data: dict, channel: str) -> None:
        """
        Handles the creation and submission to orderbook
        for a sell order

        Args:
            data (dict)
        """    
        orders = []
        orderbook = self._order_book[data['ticker']]
        
        for order_id in data['order_ids']:
            try:
                orders.append(orderbook.fetch(order_id))
            except DoesNotExist:
                pass
        
        quantity = data['quantity']
        
        for order in orders:
            if quantity <= 0: 
                break
            
            remaining_quantity = quantity - order.standing_quantity
            if remaining_quantity >= 0:
                target_quantity = order.standing_quantity                
            else:
                target_quantity = quantity
            
            quantity -= order.standing_quantity
                
            if not await self.fill_ask_order(
                order, 
                orderbook,
                channel, 
                data['price'],
                target_quantity
            ):
                break            
            
    async def fill_ask_order(
        self, 
        order: AskOrder,
        orderbook: OrderBook,
        channel: str,
        price: float,
        quantity: int
    ) -> bool:
        """
        Handles the creation, submission and calling for the ask order
        to be filled (Close request)
        
        Args:
            order_obj (_Order)
            channel (str): Channel name for pub/sub publishing
            price (float) : The requested close price
            quantity (int): Desired close quantity
        
        Returns:
            True: Order was fully filled
            False: Order was partially or not filled     
        """      
        result: tuple = self._match_ask_order(
            ticker=order.data['ticker'],
            order=order,
            orderbook=orderbook,
            bid_price=price,
            quantity=quantity
        )
        
        async def not_filled(**kwargs) -> bool:
            return False
        
        async def partial_fill(**kwargs) -> bool:
            return False
        
        async def fill(**kwargs) -> bool:
            order: BidOrder = kwargs['order']
            result: tuple = kwargs['result']
            orderbook: OrderBook = kwargs['orderbook']
            
            try:
                open_price = order.data['filled_price']
                position_size = open_price * order.data['quantity']
                pnl = (result[1] / open_price) * (order.data['quantity'] * open_price)
                order.data['realised_pnl'] +=  -1 * (position_size - round(pnl, 2))
                
                if order.standing_quantity <= 0:
                    order.data['close_price'] = result[1]
                    order.data['closed_at'] = datetime.now()
                    order.standing_quantity = 0
                    order.order_status = OrderStatus.CLOSED
                    orderbook.remove_related_orders(order.data['order_id'])
                else:
                    order.order_status = OrderStatus.PARTIALLY_CLOSED_ACTIVE

                orderbook.price = result[1]
                await batch_update([order.data])

            except Exception as e:
                logger.error(f'{type(e)} - {str(e)}')
            finally:
                return True

        return_value = await {
            0: not_filled,
            1: partial_fill,
            2: fill
        }[result[0]](result=result, order=order, orderbook=orderbook)
        
        await self._publish_update_to_client(**{
            0: {
                'channel': channel,
                'message': json.dumps({
                    "status": ConsumerMessageStatus.ERROR,
                    "message": "Insufficient bids to fulfill sell order",
                    "order_id": order.data['order_id'],
                })
            },
            1: {
                "channel": channel,
                "message": json.dumps({
                    "status": ConsumerMessageStatus.UPDATE, 
                    "message": "Insufficient bids to fulfill sell order",
                    "order_id": order.data['order_id']
                })
            },
            
            2: {
                "channel": channel,
                "message": json.dumps({
                    "status": ConsumerMessageStatus.SUCCESS,
                    'internal': OrderType.CLOSE,
                    "message": "Order successfully closed",
                    "order_id": order.data['order_id'],
                    'details': {
                        k: (str(v) if isinstance(v, (datetime, UUID)) else v) 
                        for k, v in order.data.items()
                        if k != 'user_id'
                    }
                })
            }
        }[result[0]])

        return return_value

    
    def _match_ask_order(
        self, 
        ticker: str,
        orderbook: OrderBook,
        order: APIOrder = None,
        bid_price: float = None,
        quantity: float = None,
        attempts: float = 0
    ) -> tuple[int, Optional[float]]:
        """
        Recursively calls itself if the quantity
        for the order is partially filled ( > 0). 
        Once filled it'll return 2

        Args:
            ticker (str): _description_
            order (_Order, optional): Defaults to None.
            ask_price (float, optional): Defaults to None.
            quantity (float, optional): Defaults to None.
            attempts (float, optional):  Defaults to 0.

        Returns:
            (0,): Order couldn't be filled due to insufficient bids
            (1,): Order was partially filled
            (2, bid_price): Order was successfully filled
        """        
        bid_price = orderbook.find_closest_price(bid_price, 'bid')
        if not bid_price:
            return (0, )
        
        touched_orders = []
        filled_orders = []
        
        # Fulfilling the order
        for ex_order in orderbook.bids[bid_price]:
            touched_orders.append(ex_order)         
            remaining_quantity = quantity - ex_order.standing_quantity
            
            if remaining_quantity >= 0:
                filled_orders.append(ex_order)
                ex_order.data['filled_price'] = bid_price
                order.reduce_standing_quantity(ex_order.standing_quantity)                
            else:
                ex_order.reduce_standing_quantity(quantity)
                order.reduce_standing_quantity(quantity)
                
            quantity -= ex_order.standing_quantity
            
            if quantity <= 0:
                break
        
        for item in filled_orders:
            item.order_status = OrderStatus.FILLED
            if item.data['take_profit'] is not None:
                new_order = AskOrder(item.data, _OrderType.TAKE_PROFIT_ORDER)
                orderbook.append_ask(item.data['take_profit'], new_order)
            if item.data['stop_loss']is not None:
                new_order = AskOrder(item.data, _OrderType.STOP_LOSS_ORDER)
                orderbook.append_ask(item.data['stop_loss'], new_order)
                    
        asyncio.create_task(batch_update([item.data for item in touched_orders]))    
        
        if quantity <= 0:
            return (2, bid_price)

        if attempts < self._MAX_MATCHING_ATTEMPTS:
            attempts += 1
            return self._match_ask_order(
                ticker=ticker,
                order=order,
                orderbook=orderbook,
                quantity=quantity,
                bid_price=bid_price,
                attempts=attempts,
            )
    
        return (1,)
        
    async def _handle_limit_order(self, data: dict, channel: str) -> None:
        """
        Places limit order into the bids list

        Args:
            data (dict): 
            channel (str): 
        """        
        self._order_book[data['ticker']].append_bid(BidOrder(data, _OrderType.LIMIT_ORDER), data['limit_price'])
        await self._publish_update_to_client(
            channel,
            {
                'status': ConsumerMessageStatus.SUCCESS, 
                'message': 'Limit Order placed successfully'
            }
        )
        
    async def _handle_modify_order(self, data: dict, channel: str) -> None:
        try:
            self._order_book[data['ticker']].alter_tp_sl(
                data['order_id'], 
                data['take_profit'], 
                data['stop_loss'],
            )
            
            await self._publish_update_to_client(**{
                'channel': channel,
                'message': {
                    'status': ConsumerMessageStatus.SUCCESS,
                    'message': 'Updated TP & SL'
                }
            })
        except Exception as e:
            logger.error('{} - {}'.format(type(e), str(e)))
    