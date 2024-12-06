from collections import deque
import asyncio, json, random, redis, faker, logging
from uuid import UUID

from datetime import datetime
from faker import Faker
from sqlalchemy import insert

# Local
from db_models import MarketData
from models.models import Order
from .order import _Order, BidOrder
from engine.order_manager import OrderManager
from utils.connection import RedisConnection
from utils.db import get_db_session
from enums import ConsumerMessageStatus, OrderType, OrderStatus, _OrderType
from exceptions import DoesNotExist, InvalidAction
from .config import ASK_LEVELS, ASKS, BIDS, BIDS_LEVELS, QUEUE, REDIS_HOST


logger = logging.getLogger(__name__)

REDIS_CONN_POOL = redis.asyncio.connection.ConnectionPool(
    connection_class=RedisConnection, 
    max_connections=20
)
REDIS_CLIENT = redis.asyncio.client.Redis(connection_pool=REDIS_CONN_POOL, host=REDIS_HOST)

Faker.seed(0)
faker = Faker()

class MatchingEngine:
    def __init__(self) -> None:
        self._redis = REDIS_CLIENT
        self._order_manager = OrderManager()
        self._current_price = deque()
        
        self._handlers: dict = {
            OrderType.MARKET: self._handle_market_order,
            OrderType.CLOSE: self._handle_close_order,
            OrderType.LIMIT: self._handle_limit_order,
            OrderType.MODIFY: self._handle_modify_order
        }
        

    async def _configure_bids_asks(self, quantity: int = 100, divider: int = 5) -> None:
        for i in range(quantity):
            order = BidOrder(
                {
                    'order_id': faker.pystr(), 
                    'quantity': random.randint(1, 50), 
                    'order_status': random.choice([OrderStatus.NOT_FILLED, OrderStatus.PARTIALLY_FILLED]), 
                    'created_at': datetime.now(),
                    'ticker': 'APPL',
                },
                random.choice([_OrderType.LIMIT_ORDER, _OrderType.MARKET_ORDER])
            )
            
            bid_price = random.choice([i for i in range(20, 1000, 5)])
            if order.order_type == _OrderType.LIMIT_ORDER:
                order.data['limit_price'] = bid_price
            else:
                order.data['price'] = bid_price

            tp = [None]
            tp.extend([i for i in range(100, 1000, 5)])
            order.data['take_profit'] = random.choice(tp)
            
            sl = [None]
            sl.extend([i for i  in range(20, 1000, 5)])
            order.data['stop_loss'] = random.choice(sl)
            
            BIDS[order.data['ticker']].setdefault(bid_price, deque())
            
            if i % divider == 0:
                order.data['filled_price'] = random.choice([i for i in range(100, 130, 5)])
                order.order_status = OrderStatus.FILLED
            else:
                BIDS[order.data['ticker']][bid_price].append(order)
        
    async def main(self):
        """
            Listens to messages from the to_order_book channel
            and relays to the handler
        """
        try:
            await asyncio.sleep(0.1)
            await self._configure_bids_asks(quantity=100, divider=5)
            
            await asyncio.sleep(0)
            logger.info('Listening!')
            await asyncio.gather(*[self._listen(), self._watch_price()])
        except Exception as e:
            print('engine main', type(e), str(e))
        
    async def _listen(self) -> None:
        try:
            while True:
                try:
                    message = QUEUE.get_nowait()
                    
                    if isinstance(message, dict):
                        asyncio.create_task(self._handle_incoming_message(message)) 
                        await asyncio.sleep(0.01)
                        QUEUE.task_done()
                    
                    await asyncio.sleep(0.01)
                except asyncio.queues.QueueEmpty:
                    pass
                except Exception as e:
                    print('_listen in the matching engine ', type(e), str(e))
                    pass
                finally:
                    await asyncio.sleep(0.01)
                
        except Exception as e:
            logger.error(f'_listen matching engine {type(e)} - {str(e)}')

    async def _handle_incoming_message(self, message: dict):        
        try:
            await self._handlers[message['type']](data=message, channel=f"trades_{message['user_id']}")
        except Exception as e:
            logger.error(f'handle ncomign message {type(e)} - {str(e)}')
        
                   
    async def _publish_update_to_client(self, channel: str, message: str | dict) -> None:
        """
        Publishes message to channel using REDIS

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
        Handles the creation and submission to orderbook
        for a buy order

        Args:
            data (dict).
            channel (str).
        """
        await asyncio.sleep(0.01)
        try:       
            order = BidOrder(data, _OrderType.MARKET_ORDER)
            result: tuple = await self.match_bid_order(main_order=order, ticker=order.data['ticker'])        

            async def not_filled(**kwargs):
                return
            
            async def partial_fill(**kwargs):
                data = kwargs['data']
                order = kwargs['order']
                
                try:
                    order.order_status = OrderStatus.PARTIALLY_FILLED
                    await self._order_manager.batch_update([data])
                    BIDS[data['ticker']].setdefault(data['price'], deque())
                    BIDS[data['ticker']][data['price']].append(order) # Adding to the orderbook
                except Exception as e:
                    logger.error(str(e))
        
            async def filled(**kwargs):
                data = kwargs['data']
                order = kwargs['order']
                result = kwargs['result']
                
                try:
                    data["filled_price"] = result[1]
                    order.order_status = OrderStatus.FILLED
                    order.standing_quantity = data['quantity']
                                        
                    asyncio.create_task(self._order_manager.batch_update([data]))
                    self._current_price.append(result[1])                    
                except Exception as e:
                    print('fill func, handle market', type(e), str(e))
                    logger.error(str(e))
        
            # Sending to the order manager for future reference
            await {0: not_filled, 1: partial_fill, 2: filled}[result[0]](result=result, data=data, order=order)
     
            await asyncio.gather(*[
                self._order_manager.append_entry(order),
                self._publish_update_to_client(**{
                    0: {
                        "channel": channel,
                        "message": {
                            'status': ConsumerMessageStatus.ERROR,
                            'internal': OrderType.MARKET,
                            'message': 'Isufficient asks to fiullfill bid order',
                            'details': {
                                'order_id': data['order_id']
                            }
                        }
                    },
                    1: {
                        "channel": channel,
                        "message": json.dumps({
                            "status": ConsumerMessageStatus.UPDATE, 
                            'internal': OrderType.MARKET,
                            "message": "Order partially filled",
                            'details': {
                                "order_id": data["order_id"]
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
                                for k, v in Order(**data).model_dump().items()
                            }
                        })
                    }
                }[result[0]])
            ]) 
        except Exception as e:
            print(f'handle markt order -> {type(e)} - {str(e)}')
            logger.error(f'{type(e)} - {str(e)}')
    
    async def find_ask_price_level(
        self,
        bid_price: float,
        ticker: str,
        max_attempts: int = 5,
    ):
        """
        Finds the closest ask price level with active orders
        to the bid_price

        Args:
            bid_price (float): 
            max_attempts (int, optional): Defaults to 5.

        Returns:
            Price: The ask price with the lowest distance
            None: No asks to match the bid price execution
        """
        attempt = 0
        
        while attempt < max_attempts:
            try:
                # Finding the price with the lowest distance from the bid_price
                price_map = {
                    key: abs(bid_price - key)
                    for key in list(ASK_LEVELS[ticker])
                    if key >= bid_price
                    and ASKS[ticker][key]
                }
                
                lowest_distance = min(val for _, val in price_map.items())
                
                for price, distance in price_map.items():
                    if distance == lowest_distance:
                        return price
                
                attempt += 1
            except ValueError:
                return None
        return None
    
    async def match_bid_order(
        self, 
        ticker: str,
        main_order: _Order = None,
        bid_price: float = None,
        attempts: float = 0
    ) -> tuple:
        """
        Recursively calls itself if the quantity
        for the order is partially filled ( > 0)
        . Once filled it'll return 2
        

        Args:
            data (dict)

        Returns:
            (0,): Order couldn't be filled due to insufficient asks
            (1,): Order was partially filled
            (2, ask_price): Order was successfully filled
        """
        try:
            if not bid_price:
                bid_price = main_order.data["price"]
                
            ask_price = await self.find_ask_price_level(bid_price, ticker=ticker)
            if not ask_price:
                return (0, )

            closed_orders = []
            touched_orders = []
            
            for ex_order in ASKS[ticker][ask_price]:                    
                touched_orders.append(ex_order)
                remaining_quantity = main_order.standing_quantity - ex_order.standing_quantity
                
                # Existing order is fully consumed
                if remaining_quantity >= 0:
                    main_order.reduce_standing_quantity(ex_order.standing_quantity)
                    
                    closed_orders.append(ex_order)
                    ex_order.standing_quantity = 0
                    ex_order.data['close_price'] = ask_price
                    ex_order.data['closed_at'] = datetime.now()

                # Existing order not fully consumed
                else:
                    ex_order.reduce_standing_quantity(main_order.standing_quantity)
                    main_order.standing_quantity = 0
                    
                    if ex_order.order_type in [_OrderType.TAKE_PROFIT_ORDER, _OrderType.STOP_LOSS_ORDER]:
                        ex_order.order_status = OrderStatus.PARTIALLY_CLOSED
                    else: # this was a user submitted close request: _OrderType.CLOSE_ORDER
                        ex_order.order_status = OrderStatus.PARTIALLY_CLOSED_ACTIVE
                        
                if main_order.standing_quantity == 0:
                    break

            count = 0
            for item in closed_orders:
                try:
                    item.order_status = OrderStatus.CLOSED
                except ValueError:
                    count += 1
                    pass
            
            asyncio.create_task(self._order_manager.batch_update([item.data for item in touched_orders]))    
            if main_order.standing_quantity == 0:
                return (2, ask_price)

            if attempts < 20:
                attempts += 1
                return await self.match_bid_order(
                    ticker,
                    main_order,
                    bid_price,
                    attempts
                )
        
            return (1,)
        except Exception as e:
            print(f'match bid order -> {type(e)} - {str(e)}')
            logger.error(f'{type(e)} - {str(e)}')
    
    async def _handle_limit_order(self, channel: str, data: dict) -> None:
        """
        Places a bid order on the desired price
        for the limit order along with placing the TP and SL of the order

        Args:
            order (dict)
        """        
        
        try:
            order = BidOrder(data, _OrderType.LIMIT_ORDER)
            BIDS[data['ticker']][data['limit_price']].append(order)
            
            await asyncio.gather(*[
                self._order_manager.append_entry(order),
                self._publish_update_to_client(
                    channel=channel,
                    message=json.dumps({
                        'status': 'success',
                        'message': 'Limit order created successfully',
                        'order_id': data['order_id'],
                        "details": {
                            k: (str(v) if isinstance(v, (datetime, UUID)) else v) 
                            for k, v in Order(**data).model_dump().items()
                        }
                    })
                )
            ])
        except Exception as e:
            print('Limit handler => ', type(e), str(e))
            logger.error(str(e))
    
    async def _handle_close_order(self, data: dict, channel: str) -> None:
        """
        Handles the creation and submission to orderbook
        for a sell order

        Args:
            data (dict)
        """    
        orders = deque()
        for order_id in data['order_ids']:
            try:
                orders.append(self._order_manager.retrieve_entry(order_id))
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
                order_obj=order, 
                channel=channel, 
                price=data['price'],
                quantity=target_quantity
            ):
                break
            
    async def fill_ask_order(
        self, 
        order_obj: _Order,
        channel: str,
        price: float,
        quantity: int
    ):
        """
        Handles the creation, submission and calling for the ask order
        to be filled
        Args:
            data (dict): 
            channel (str): 
        """      
        result: tuple = await self.match_ask_order(
            ticker=order_obj.data['ticker'],
            main_order=order_obj,
            ask_price=price,
            quantity=quantity
        )
        
        async def not_filled(**kwargs) -> bool:
            return False
        
        async def partial_fill(**kwargs) -> bool:
            return False
        
        async def fill(**kwargs) -> bool:
            order: _Order = kwargs['order']
            result: tuple = kwargs['result']
            
            try:
                open_price = order.data['filled_price']
                pnl = (price / open_price) * (quantity * open_price)
                order.data['realised_pnl'] += round(pnl, 2)
                
                if order.standing_quantity == 0:
                    order.data['close_price'] = result[1]
                    order.data['closed_at'] = datetime.now()
                    order.order_status = OrderStatus.CLOSED
                else:
                    order.order_status = OrderStatus.PARTIALLY_CLOSED_ACTIVE

                self._current_price.append(result[1])
                await self._order_manager.batch_update([order.data])

            except Exception as e:
                print('fill ask order -- fill -> ', type(e), str(e))
            finally:
                return True

        return_value = await {
            0: not_filled,
            1: partial_fill,
            2: fill
        }[result[0]](result=result, order=order_obj)
        
        await self._publish_update_to_client(**{
            0: {
                'channel': channel,
                'message': json.dumps({
                    "status": ConsumerMessageStatus.ERROR,
                    "message": "Insufficient bids to fulfill sell order",
                    "order_id": order_obj.data['order_id'],
                })
            },
            1: {
                "channel": channel,
                "message": json.dumps({
                    "status": ConsumerMessageStatus.UPDATE, 
                    "message": "Order partially closed",
                    "order_id": order_obj.data['order_id']
                })
            },
            
            2: {
                "channel": channel,
                "message": json.dumps({
                    "status": ConsumerMessageStatus.SUCCESS,
                    'internal': OrderType.CLOSE,
                    "message": "Order successfully closed",
                    "order_id": order_obj.data['order_id'],
                    'details': {
                        k: (str(v) if isinstance(v, (datetime, UUID)) else v) 
                        for k, v in order_obj.data.items()
                        if k != 'user_id'
                    }
                })
            }
        }[result[0]])

        return return_value
    
    async def find_bid_price_level(
      self,
      ask_price: float,
      ticker: str,
      max_attempts: int = 5  
    ):
        """
        Finds the closest bid price level with active orders
        to the ask_price

        Args:
            bid_price (float): 
            max_attempts (int, optional): Defaults to 5.

        Returns:
            Price: The ask price with the lowest distance
            None: No asks to match the bid price execution
        """
        attempt = 0
        while attempt < max_attempts:
            try:
                # Finding the price with the lowest distance from the ask_price
                price_map = {
                    key: abs(ask_price - key)
                    for key in BIDS_LEVELS[ticker]
                    if key <= ask_price
                    and BIDS[ticker][key]
                }
                
                lowest_distance = min(val for _, val in price_map.items())
                
                for price, distance in price_map.items():
                    if distance == lowest_distance:
                        return price
                
                attempt += 1
            except ValueError:
                return None
        return None
    
    async def match_ask_order(
        self, 
        ticker: str,
        main_order: Order = None,
        ask_price: float = None,
        quantity: float = None,
        attempts: float = 0
    ) -> tuple:
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
        
        bid_price = await self.find_bid_price_level(ask_price, ticker=ticker)
        if not bid_price:
            return (0, )
        
        touched_orders = []
        filled_orders = []
        
        # Fulfilling the order
        for ex_order in BIDS[ticker][bid_price]:
            touched_orders.append(ex_order)                
            remaining_quantity = quantity - ex_order.standing_quantity
            
            if remaining_quantity >= 0:
                filled_orders.append(ex_order)
                ex_order.data['filled_price'] = bid_price
                main_order.reduce_standing_quantity(ex_order.standing_quantity)
            else:
                ex_order.reduce_standing_quantity(quantity)
                main_order.reduce_standing_quantity(quantity)
                
            quantity -= ex_order.standing_quantity
            
            if quantity <= 0:
                break
        
        for item in filled_orders:
            item.order_status = OrderStatus.FILLED
        
        asyncio.create_task(self._order_manager.batch_update([item.data for item in touched_orders]))    
        
        if quantity <= 0:
            return (2, bid_price)

        if attempts < 20:
            attempts += 1
            return await self.match_ask_order(
                ticker,
                main_order,
                bid_price,
                attempts
            )
    
        return (1,)
        
    async def _handle_limit_order(self, data: dict, channel: str) -> None:
        """
        Places limit order into the bids list

        Args:
            data (dict): 
            channel (str): 
        """        
        BIDS[data['ticker']][data['limit_price']].append(BidOrder(data, _OrderType.LIMIT_ORDER))
        await self._publish_update_to_client(
            channel,
            {'status': ConsumerMessageStatus.SUCCESS, 'message': 'Limit Order placed successfully'}
        )
        
    async def _handle_modify_order(self, data: dict, channel: str) -> None:
        await self._order_manager.alter_tp_sl(data['order_id'], data['take_profit'], data['stop_loss'])
        await self._publish_update_to_client(**{
            'channel': channel,
            'message': {
                'status': ConsumerMessageStatus.SUCCESS,
                'message': 'Updated TP & SL'
            }
        })
    
    
    async def add_new_price_to_db(self, new_price: float, ticker: str, new_time: int) -> None:
        """
        Creates a new record in the DB of the price
        Args:
            new_price (float):
            ticker (str): 
            new_time (int): UNIX Timestamp
        """        
        async with get_db_session() as session:
            await session.execute(
                insert(MarketData)
                .values(
                    ticker=ticker,
                    date=new_time,
                    price=new_price
                )
            )
            await session.commit()

    async def _watch_price(self) -> None:

        async def _broadcast_price_change(new_price: float):
            try:
                QUEUE.put_nowait(new_price)
                await asyncio.sleep(0)
            except Exception as e:
                print('broadcast price change -> ', type(e), str(e))

        await asyncio.sleep(0.1)

        try:
            while True:
                try:
                    item = self._current_price.popleft()
                    await _broadcast_price_change(item)
                    await self.add_new_price_to_db(
                        new_price=item, 
                        ticker='APPL', 
                        new_time=int(datetime.now().timestamp())
                    )
                except IndexError:
                    pass
                except Exception as e:
                    print('watch price: ', type(e), str(e))
                finally:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print('watch price', type(e), str(e))


def run():
    ENGINE = MatchingEngine()
    asyncio.run(ENGINE.main())

