import asyncio 
import json
import time 
import redis 
import logging
import queue

from datetime import datetime
from typing import Optional
from multiprocessing import Queue

# Local
from config import REDIS_HOST, ASYNC_REDIS_CONN_POOL
from enums import (
    PubSubCategory, 
    OrderType, 
    OrderStatus, 
    UpdateScope
)
from models.models import APIOrder
from exceptions import DoesNotExist
from models.socket_models import BasePubSubMessage, OrderUpdatePubSubMessage
from ..enums import OrderType as _OrderType
from ..orderbook import OrderBook
from ..utils import batch_update, publish_update_to_client
from ..order.bid import BidOrder
from ..order.ask import AskOrder


logger = logging.getLogger(__name__)


class SpotEngine:
    _MAX_MATCHING_ATTEMPTS = 20
    _MAX_PRICE_LEVEL_ATTEMPTS = 5

    def __init__(self, queue=Queue) -> None:
        self.queue = queue
        self._order_books: dict[str, OrderBook] = {}
        self._redis = redis.asyncio.client.Redis(
            connection_pool=ASYNC_REDIS_CONN_POOL, 
            host=REDIS_HOST
        )
        self._handlers: dict = {
            OrderType.MARKET: self._handle_market_order,
            OrderType.CLOSE: self._handle_close_order,
            OrderType.LIMIT: self._handle_limit_order,
            OrderType.MODIFY: self._handle_modify_order,
        }

    async def start(self, **kwargs) -> None:
        """
        Listens to messages from the to_order_book channel
        and relays to the handler
        
        Args:
            kwargs (dict):
             - price_queue (multiprocessing.Queue): Used for the orderbook creation
        """
        try: 
            self._order_books['APPL'] = OrderBook('APPL', kwargs['price_queue'])
            self._order_books['APPL']._configure_bid_asks(10_000, 2)

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
                message = self.queue.get_nowait()
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

    async def _handle_market_order(self, data: dict, channel: str) -> None:
        """
        Central point for matching bid against asks
        as well as user notifications

        Args:
            data (dict).
            channel (str).
        """
        await asyncio.sleep(0.01)
        orderbook = self._order_books[data['ticker']]
        
        try:       
            order = BidOrder(data, _OrderType.MARKET_ORDER)
            orderbook.track(order=order) 
            result: tuple = self._match_bid_order(
                order=order, 
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
                    orderbook.track(order=order)
                    order.append_to_orderbook(orderbook, order.data['price'])
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
                        orderbook.track(order=new_order, channel='take_profit')
                        new_order.append_to_orderbook(orderbook)
                        
                    if order.data['stop_loss'] is not None:
                        new_order = AskOrder(order.data, _OrderType.STOP_LOSS_ORDER)
                        orderbook.track(order=new_order, channel='stop_loss')
                        order.append_to_orderbook(orderbook)
                    
                    asyncio.create_task(batch_update([data]))
                    await asyncio.sleep(0)

                    await orderbook.set_price(result[1])
                except Exception as e:
                    logger.error(f'{type(e)} - {str(e)}')
        
            await {0: not_filled, 1: partial_fill, 2: filled}[result[0]]\
                (result=result, data=data, order=order, orderbook=orderbook)
     
            orderbook.track(order=order)
            order.append_to_orderbook(orderbook)
        
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
                            details=APIOrder(**data).model_dump()
                        ).model_dump()
                    },
                    
                    2: {
                        "channel": channel,
                        'message': BasePubSubMessage(
                            category=PubSubCategory.SUCCESS,
                            message="Order successfully placed",
                            details=APIOrder(**data).model_dump()
                        ).model_dump()
                    }
                }[result[0]])
        except Exception as e:
            logger.error(f'{type(e)} - {str(e)}')
    
    def _match_bid_order(self, **kwargs) -> tuple:
        """
        Matches quantity from main
        
        Args:
            orderbook (OrderBook)
            order (BidOrder)

        Returns:
            (0,): Order couldn't be filled due to insufficient asks
            (1,): Order was partially filled
            (2, ask_price): Order was successfully filled
        """
        orderbook: OrderBook = kwargs['orderbook']
        order: BidOrder = kwargs['order']
        bid_price: float = kwargs.get('bid_price', None) or order.data['price']
        attempts: int = kwargs.get('attempts', None) or 0
        
        ask_price = orderbook.find_closest_price(bid_price, 'asks')
        if ask_price is None:
            return (0,)

        closed_orders = []
        touched_orders = []            
        
        ex_order: AskOrder
        for ex_order in orderbook.asks[ask_price]:
            try:
                touched_orders.append(ex_order)
                leftover_quant = order.standing_quantity - ex_order.standing_quantity
                
                if leftover_quant >= 0:
                    order.reduce_standing_quantity(ex_order.standing_quantity)
                    ex_order.reduce_standing_quantity(ex_order.standing_quantity)
                    
                    ex_order.data['close_price'] = ask_price
                    ex_order.data['closed_at'] = datetime.now()

                    closed_orders.append(ex_order)
                else:
                    ex_order.reduce_standing_quantity(order.standing_quantity)
                    order.reduce_standing_quantity(order.standing_quantity)
                    
                    if ex_order.order_type in [_OrderType.TAKE_PROFIT_ORDER, _OrderType.STOP_LOSS_ORDER]:
                        ex_order.order_status = OrderStatus.PARTIALLY_CLOSED_INACTIVE
                    else:
                        ex_order.order_status = OrderStatus.PARTIALLY_CLOSED_ACTIVE
                        
                if order.standing_quantity == 0:
                    break
                
            except Exception as e:
                import traceback
                logger.error(f'Error whilst matching against existing ask order {traceback.extract_tb(e.__traceback__)[-1].line} {type(e)} - {str(e)}')

        try:                
            for ex_order in closed_orders:
                try:
                    ex_order.order_status = OrderStatus.CLOSED
                    orderbook.rtrack(order=ex_order, channel='all')
                    ex_order.remove_from_orderbook(orderbook)
                except ValueError:
                    pass
            
            asyncio.create_task(batch_update([item.data for item in touched_orders]))    
        except Exception as e:
            import traceback
            logger.error(f'Error during handling of closed and filled ask orders: {traceback.extract_tb(e.__traceback__)[-1].line} {type(e)} - {str(e)}')

        if order.standing_quantity == 0:
            return (2, ask_price)

        if attempts < self._MAX_MATCHING_ATTEMPTS:
            attempts += 1
            return self._match_bid_order(
                orderbook=orderbook,
                order=order,
                bid_price=bid_price,
                attempts=attempts
            )

        return (1,)
    
    async def _handle_limit_order(self, channel: str, data: dict) -> None:
        """
        Places a bid order on the desired price
        for the limit order along with placing the TP and SL of the order

        Args:
            order (dict)
        """        
        
        try:
            order = BidOrder(data, _OrderType.LIMIT_ORDER)
            self._order_books[data['ticker']].track(order=order, )
            order.append_to_orderbook(self._order_books[data['ticker']], order.data['limit_price'])
            
            await publish_update_to_client(
                channel=channel,
                message=BasePubSubMessage(
                    category=PubSubCategory.SUCCESS,
                    message="Limit order placed succesfully",
                    details=APIOrder(**data).model_dump()
                ).model_dump()
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
        orderbook = self._order_books[data['ticker']]
        
        for order_id in data['order_ids']:
            try:
                orders.append(orderbook.fetch(order_id))
            except DoesNotExist:
                pass
        
        quantity = data['quantity']
        
        for order in orders:
            try:
                if quantity <= 0: 
                    break
                
                remaining_quantity = quantity - order.standing_quantity
                
                if remaining_quantity >= 0:
                    target_quantity = order.standing_quantity                
                else:
                    target_quantity = quantity
                
                quantity -= order.standing_quantity
                    
                if not await self._fill_ask_order(
                    order=order, 
                    orderbook=orderbook,
                    channel=channel, 
                    price=data['price'],
                    quantity=target_quantity,
                ):
                    break            
            except Exception as e:
                logger.error('Error during pre-process: {} - {}'.format(type(e), str(e)))
            
    async def _fill_ask_order(
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
            order (AskOrder): 
            orderbook (OrderBook): 
            channel (str): PubSub channel
            price (float): price level to find opposing orders
            quantity (int): quantity to be closed

        Returns:
            True: Order was fully filled
            False: Order was partially or not filled   
        """        
        try: 
            try:   
                result: tuple = self._match_ask_order(
                    order=order,
                    orderbook=orderbook,
                    bid_price=price,
                    quantity=quantity
                )
            except Exception as e:
                logger.error('her her her {} - {}'.format(type(e), str(e)))
            async def rfalse():
                return False
            
            async def fill(**kwargs) -> bool:
                order: BidOrder = kwargs['order']
                result: tuple = kwargs['result']
                orderbook: OrderBook = kwargs['orderbook']
                
                try:
                    open_price = order.data['filled_price']
                    position_size = open_price * order.data['quantity']
                    pnl = (result[1] / open_price) * (position_size)
                    order.data['realised_pnl'] +=  -1 * (position_size - round(pnl, 2))
                    
                    if order.standing_quantity <= 0:
                        order.data['close_price'] = result[1]
                        order.data['closed_at'] = datetime.now()
                        order.reduce_standing_quantity(order.standing_quantity)
                        order.order_status = OrderStatus.CLOSED
                        orderbook.rtrack(order=order, channel='all')
                    else:
                        order.order_status = OrderStatus.PARTIALLY_CLOSED_ACTIVE
                    
                    await orderbook.set_price(result[1])
                    await batch_update([order.data])

                except Exception as e:
                    logger.error(f'Fill: {type(e)} - {str(e)}')
                finally:
                    return True

            return_value = await {
                0: rfalse,
                1: rfalse,
                2: fill
            }[result[0]](result=result, order=order, orderbook=orderbook)
            
            await publish_update_to_client(**{
                0: {
                    'channel': channel,
                    'message': BasePubSubMessage(
                        category=PubSubCategory.ERROR, 
                        message="Insufficient bids to fulfill sell order"
                    ).model_dump()
                },
                
                1: {
                    "channel": channel,
                    'message': BasePubSubMessage(
                        category=PubSubCategory.ERROR, 
                        message="Insufficient bids to fulfill sell order"
                    ).model_dump()
                },
                
                2: {
                    "channel": channel,
                    'message': BasePubSubMessage(
                        category=PubSubCategory.ORDER_UPDATE,
                        on=UpdateScope.EXISTING,
                        message='Order closed successfully',
                        details=APIOrder(**order.data).model_dump()
                    ).model_dump()
                }
            }[result[0]])

            return return_value
        except Exception as e:
            logger.error('{} - {}'.format(type(e), str(e)))

    
    def _match_ask_order(self, **kwargs) -> tuple[int, Optional[float]]:
        """
        Recursively calls itself if the quantity
        for the order is partially filled ( > 0). 
        Once filled it'll return 2

        Args:
            orderbook (OrderBook)
            order (AskOrder): Order to be closed
            quantity (int): Quantity to be closed
            bid_price (float): Bid price to find closing orders

        Returns:
            (0,): Order couldn't be filled due to insufficient bids
            (1,): Order was partially filled
            (2, bid_price): Order was successfully filled
        """        
        orderbook: OrderBook = kwargs['orderbook']
        order: AskOrder = kwargs['order']
        quantity: int = kwargs['quantity']
        attempts = 0 if 'attempts' not in kwargs else kwargs['attempts']
        
        bid_price = orderbook.find_closest_price(kwargs['bid_price'], 'bids')
        
        if not bid_price:
            return (0, )
        
        touched_orders = []
        filled_orders = []
        
        # Fulfilling the order
        ex_order: BidOrder
        for ex_order in orderbook.bids[bid_price]:
            try:
                touched_orders.append(ex_order)         
                remaining_quantity = quantity - ex_order.standing_quantity
                
                if remaining_quantity >= 0:
                    filled_orders.append(ex_order)
                    order.reduce_standing_quantity(ex_order.standing_quantity)                
                    ex_order.reduce_standing_quantity(ex_order.standing_quantity)
                else:
                    ex_order.reduce_standing_quantity(quantity)
                    order.reduce_standing_quantity(quantity)
                    
                quantity = remaining_quantity
                
                if quantity <= 0:
                    break
            except Exception as e:
                logger.error('Error matching against existing bid order: {} - {}'.format(type(e), str(e)))
        
        try:
            
            for ex_order in filled_orders:
                ex_order.data['filled_price'] = bid_price
                ex_order.order_status = OrderStatus.FILLED
                ex_order.remove_from_orderbook(orderbook)
                
                orderbook.track(order=ex_order)
                
                if ex_order.data['take_profit'] is not None:
                    new_order = AskOrder(ex_order.data, _OrderType.TAKE_PROFIT_ORDER)
                    orderbook.track(order=new_order, channel='take_profit')
                    new_order.append_to_orderbook(orderbook, ex_order.data['take_profit'])
                    
                if ex_order.data['stop_loss'] is not None:
                    new_order = AskOrder(ex_order.data, _OrderType.STOP_LOSS_ORDER)
                    orderbook.track(order=new_order, channel='stop_loss')
                    new_order.append_to_orderbook(orderbook, ex_order.data['stop_loss'])
                        
            asyncio.create_task(batch_update([item.data for item in touched_orders]))    
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(
                'Error during handling of closed and filled bid orders: {} - {}'.format(type(e), str(e)),
            )
        
        if quantity <= 0:
            return (2, bid_price)

        if attempts < self._MAX_MATCHING_ATTEMPTS:
            attempts += 1
            return self._match_ask_order(
                orderbook=orderbook,
                order=order,
                quantity=quantity,
                attempts=attempts,
                bid_price=bid_price
            )
    
        return (1,)
            
    async def _handle_modify_order(self, data: dict, channel: str) -> None:
        try:
            self._order_books[data['ticker']].alter_tp_sl(
                data['order_id'], 
                data['take_profit'], 
                data['stop_loss'],
            )
            
            await publish_update_to_client(**{
                'channel': channel,
                'message': BasePubSubMessage(
                    category=PubSubCategory.SUCCESS,
                    message="Limit Order placed successfully"
                ).model_dump()
            })
        except Exception as e:
            logger.error('{} - {}'.format(type(e), str(e)))
    