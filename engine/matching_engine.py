import asyncio, json, random, redis, faker
from uuid import UUID

from datetime import datetime
from faker import Faker
from sqlalchemy import insert

# Local
from db_models import MarketData
from models.models import Order
from ._order import _Order, AskOrder, BidOrder
from engine.order_manager import OrderManager
from utils.connection import RedisConnection
from utils.db import get_db_session
from enums import ConsumerStatusType, OrderType, OrderStatus, _OrderType
from exceptions import DoesNotExist, InvalidAction
from .config import ASK_LEVELS, ASKS, BIDS, BIDS_LEVELS, REDIS_HOST


REDIS_CONN_POOL = redis.asyncio.connection.ConnectionPool(
    connection_class=RedisConnection, 
    max_connections=20
)
REDIS_CLIENT = redis.asyncio.client.Redis(connection_pool=REDIS_CONN_POOL, host=REDIS_HOST)

Faker.seed(0)
faker = Faker()

class MatchingEngine:
    def __init__(self):
        self.redis = REDIS_CLIENT
        self.order_manager = OrderManager()
        self._current_price: float = None        

    async def configure_bids_asks(self, quantity: int = 100, divider: int = 5) -> None:
        for i in range(quantity):
            order = BidOrder(
                {
                    'order_id': faker.pystr(), 
                    'quantity': random.randint(1, 20), 
                    'order_status': random.choice([OrderStatus.NOT_FILLED, OrderStatus.PARTIALLY_FILLED]), 
                    'created_at': datetime.now(),
                    'ticker': 'APPL',
                },
                random.choice([_OrderType.LIMIT_ORDER, _OrderType.MARKET_ORDER])
            )
            
            bid_price = random.choice([i for i in range(90, 170, 5)])
            if order.order_type == _OrderType.LIMIT_ORDER:
                order.data['limit_price'] = bid_price
            else:
                order.data['price'] = bid_price

            tp = [None]
            tp.extend([i for i in range(120, 150, 5)])
            order.data['take_profit'] = random.choice(tp)
            
            sl = [None]
            sl.extend([i for i  in range(60, 105, 5)])
            order.data['stop_loss'] = random.choice(sl)
            
            BIDS[order.data['ticker']].setdefault(bid_price, [])
            
            if i % divider == 0:
                order.data['filled_price'] = random.choice([i for i in range(100, 130, 5)])
                order.order_status = OrderStatus.FILLED
            else:
                BIDS[order.data['ticker']][bid_price].append(order)
            

    @property
    def current_price(self):
        return self._current_price

    @current_price.setter
    def current_price(self, value: float):
        asyncio.create_task(self.on_price_change(value))
        self._current_price = value
    
    async def on_price_change(self, new_price: float):
        """
        Publishes a message to all users when the price changes

        Args:
            new_price (float):
        """        
        await self.redis.publish(channel='prices', message=json.dumps({'ticker': 'APPL', 'price': new_price, 'time': int(datetime.now().timestamp())}))
        
        
    async def listen_to_client_events(self):
        """
            Listens to messages from the to_order_book channel
            and relays to the handler
        """
        await self.configure_bids_asks()
        
        async with self.redis.pubsub() as pubsub:
            await pubsub.subscribe("to_order_book")
            print('Listening for orders...')
    
            async for message in pubsub.listen():
                await asyncio.sleep(0.01)
                if message.get("type", None) == "message":
                    asyncio.create_task(self.handle_incoming_message(message["data"]))
                    

    async def handle_incoming_message(self, data: dict):
        """
        Handles the routing of the request into the right
        functions

        Args:
            data (dict): A dictionary representation of the request
        """        
        data = json.loads(data)
        action_type = data["type"]
        channel = f"trades_{data['user_id']}"
        
        await {
            OrderType.MARKET: self.handle_market_order,
            OrderType.CLOSE: self.handle_close_order,
            OrderType.LIMIT: self.handle_limit_order,
            OrderType.MODIFY: self.handle_modify_order
        }.get(action_type)(data, channel)

                   
    async def publish_update_to_client(self, channel: str, message: str | dict) -> None:
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
                await self.redis.publish(channel=channel, message=message)
        except Exception as e:
            print("Publish update to client:", type(e), end=f"\n{str(e)}\n")
            print('-' * 10)
            pass
            
    
    async def handle_market_order(self, data: dict, channel: str) -> None:
        """
        Handles the creation and submission to orderbook
        for a buy order

        Args:
            data (dict).
            channel (str).
        """
        order = BidOrder(data, _OrderType.MARKET_ORDER)
        result: tuple = await self.match_bid_order(main_order=order, ticker=order.data['ticker'])        
        
        if result[0] == 0:
            await self.configure_bids_asks()
            self.current_price *= 0.7

        
        async def not_filled(**kwargs):
            return
        
        async def partial_fill(**kwargs):
            try:
                order.order_status = OrderStatus.PARTIALLY_FILLED
                await self.order_manager.batch_update([data])
                BIDS[order.data['ticker']].setdefault(order.data['price'], [])
                BIDS[order.data['ticker']][order.data['price']].append(order) # Adding to the orderbook
            except Exception as e:
                print('partial fill error:', str(e))
        
        async def filled(**kwargs):
            data = kwargs['data']
            target_order = kwargs['target_order']
            result = kwargs['result']
            
            try:
                kwargs['data']["filled_price"] = result[1]
                target_order.order_status = OrderStatus.FILLED
                target_order.standing_quantity = data['quantity']
                await self.order_manager.batch_update([data])
                
                self.current_price = result[1]
                await self.add_new_price_to_db(result[1], data['ticker'], int(datetime.now().timestamp()))
            except Exception as e:
                print('Filled market order error:', str(e))
                
        # Sending to the order manager for future reference
        await self.order_manager.append_entry(order)
        
        await {0: not_filled, 1: partial_fill, 2: filled}.get(result[0])(result=result, target_order=order, data=data)
        
        await self.publish_update_to_client(**{
            0: {
                "channel": channel,
                "message": {
                    'status': ConsumerStatusType.ERROR,
                    'message': 'Isufficient asks to fiullfill bid order',
                    'order_id': data['order_id']
                }
            },
            1: {
                "channel": channel,
                "message": json.dumps({
                    "status": ConsumerStatusType.UPDATE, 
                    "message": "Order partially filled",
                    "order_id": data["order_id"]
                })
            },
            2: {
                "channel": channel,
                "message": json.dumps({
                    "status": ConsumerStatusType.SUCCESS,
                    "message": "Order successfully placed",
                    "details": {
                        k: (str(v) if isinstance(v, (datetime, UUID)) else v) for k, v in Order(**data).model_dump().items()
                    }
                })
            }
        }.get(result[0]))
        
    
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
        
        asyncio.create_task(self.order_manager.batch_update([item.data for item in touched_orders]))    
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
                
    
    async def handle_limit_order(self, channel: str, data: dict) -> None:
        """
        Places a bid order on the desired price
        for the limit order along with placing the TP and SL of the order

        Args:
            order (dict)
        """        
        
        try:
            order = BidOrder(data, _OrderType.LIMIT_ORDER)

            BIDS[data['ticker']][data['limit_price']].append(order)
            
            # await self.place_tp_sl(data)
            await self.order_manager.append_entry(order)
            
            await self.publish_update_to_client(
                channel=channel,
                message=json.dumps({
                    'status': 'success',
                    'message': 'Limit order created successfully',
                    'order_id': data['order_id']
                })
            )
        except Exception as e:
            print('handle limit order error:', str(e))
        
        # except (InvalidAction, DoesNotExist) as e:
        #     await self.publish_update_to_client(channel=channel, message=json.dumps({
        #             'status': 'error',
        #             'message': str(e),
        #             'order_id': data['order_id']
        #         }))
        
    
    async def handle_close_order(self, data: dict, channel: str) -> None:
        """
        Handles the creation and submission to orderbook
        for a sell order

        Args:
            data (dict)
        """    
        orders = []
        
        for order_id in data['order_ids']:
            try:
                orders.append(self.order_manager.retrieve_entry(order_id))
            except AttributeError:
                pass
            finally:
                continue

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

        # Relaying message to user
        status_message = {
            0: {
                'channel': channel,
                'message': json.dumps({
                    "status": ConsumerStatusType.ERROR,
                    "message": "Insufficient bids to fulfill sell order",
                    "order_id": order_obj.data['order_id']
                })
            },
            1: {
                "channel": channel,
                "message": json.dumps({
                    "status": ConsumerStatusType.UPDATE, 
                    "message": "Order partially closed",
                    "order_id": order_obj.data['order_id']
                })
            },
            
            2: {
                "channel": channel,
                "message": json.dumps({
                    "status": ConsumerStatusType.SUCCESS,
                    "message": "Order successfully closed",
                    "order_id": order_obj.data['order_id']
                })
            }
        }.get(result[0])
        
        await self.publish_update_to_client(**status_message)

        if result[0] == 0:
            return False

        # Order was successfully closed
        if result[0] == 2:
            try:
                open_price = order_obj.data['filled_price']
                pnl = (price / open_price) * (quantity * open_price)
                order_obj.data['realised_pnl'] += pnl
                
                if order_obj.standing_quantity == 0:
                    order_obj.data['close_price'] = result[1]
                    order_obj.data['closed_at'] = datetime.now()
                    order_obj.order_status = OrderStatus.CLOSED
                else:
                    order_obj.order_status = OrderStatus.PARTIALLY_CLOSED_ACTIVE

                await self.order_manager.batch_update([order_obj.data])
                
                self.current_price = result[1]
                await self.add_new_price_to_db(result[1], order_obj.data['ticker'], int(datetime.now().timestamp()))
            except InvalidAction as e:
                print("Error in handling buy order\n", str(e))
                print('-' * 10)
                await self.publish_update_to_client(channel=channel, message=str(e))
            finally:
                return True
        
        
        # Order was partially closed so we add to orderbook
        # print('Close order partially closed')
        # order_obj.order_status = OrderStatus.PARTIALLY_CLOSED
        # await self.order_manager.batch_update([order_obj.data])
        # self.asks[order_obj.data['ticker']][price].append(order_obj)
        return False
    
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
        main_order: _Order = None,
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
        
        asyncio.create_task(self.order_manager.batch_update([item.data for item in touched_orders]))    
        
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
        
    
    async def handle_limit_order(self, data: dict, channel: str) -> None:
        """
        Places limit order into the bids list

        Args:
            data (dict): 
            channel (str): 
        """        
        BIDS[data['ticker']][data['limit_price']].append(BidOrder(data, _OrderType.LIMIT_ORDER))
        await self.publish_update_to_client(
            channel,
            {'status': ConsumerStatusType.SUCCESS, 'message': 'Limit Order placed successfully'}
        )
        
    async def handle_modify_order(self, data: dict, channel: str) -> None:
        await self.order_manager.alter_tp_sl(data['order_id'], data['take_profit'], data['stop_loss'])
        await self.publish_update_to_client(**{
            'channel': channel,
            'message': {
                'status': ConsumerStatusType.SUCCESS,
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


def run():
    engine = MatchingEngine()
    asyncio.run(engine.listen_to_client_events())
