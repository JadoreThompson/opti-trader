import asyncio, json, random, redis, faker

from datetime import datetime
from faker import Faker
from sqlalchemy import insert

# Local
from db_models import MarketData
from engine._order import _Order
from engine.order_manager import OrderManager
from utils.connection import RedisConnection
from utils.db import get_db_session
from enums import ConsumerStatusType, OrderType, OrderStatus, _OrderType
from exceptions import DoesNotExist, InvalidAction
from .config import REDIS_HOST


REDIS_CONN_POOL = redis.asyncio.connection.ConnectionPool(
    connection_class=RedisConnection, 
    max_connections=20
)
REDIS_CLIENT = redis.asyncio.client.Redis(connection_pool=REDIS_CONN_POOL, host=REDIS_HOST)

Faker.seed(0)
faker = Faker()

class MatchingEngine:
    def __init__(self):
        """
        Bids and asks data structure
        {
            ticker: {
                price: [_Order()]
            }
        }
        """
        self.redis = REDIS_CLIENT
        self.order_manager = OrderManager()

        ask_quant = 100
        ask_range = range(110, 150, 5)
        self.asks: dict[str, dict[float, list[_Order]]] = {
            'APPL': {
                price: [
                        _Order(
                            {'order_id': faker.pystr(), 'quantity': random.randint(20, 50), 'order_status': random.choice([OrderStatus.PARTIALLY_CLOSED,]), 'created_at': datetime.now()},
                            random.choice([_OrderType.TAKE_PROFIT_ORDER, _OrderType.STOP_LOSS_ORDER])
                        ) for _ in range(ask_quant)
                    ]
                for price in ask_range
            }
        }
        
        bids_quant = 2
        bid_range = range(70, 150, 2)
        self.bids: dict[str, dict[float, list[_Order]]] = {
            'APPL': {
                price: [
                        _Order(
                            {'order_id': faker.pystr(), 'quantity': random.randint(5, 10), 'order_status': OrderStatus.NOT_FILLED, 'created_at': datetime.now()},
                            random.choice([_OrderType.MARKET_ORDER, _OrderType.LIMIT_ORDER])
                        ) for _ in range(bids_quant)
                    ]
                for price in bid_range
            }
        }

        
        self.bids_price_levels = {key: self.bids[key].keys() for key in self.bids}
        self.asks_price_levels = {key: self.asks[key].keys() for key in self.asks}
        
        self._current_price: float = None        


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
        print('Current Price: ', self._current_price)
        
    async def listen_to_client_events(self):
        """
            Listens to messages from the to_order_book channel
            and relays to the handler
        """        
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
        
        options = {
            OrderType.MARKET: self.handle_market_order,
            OrderType.CLOSE: self.handle_close_order,
            OrderType.LIMIT: self.handle_limit_order
        }
        
        await options.get(action_type)(data, channel)
                   
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
    
    
    async def place_tp_sl(self, data: dict) -> None:
        try:
            # TP
            if data.get('take_profit', None):
                tp_order = _Order(data, _OrderType.TAKE_PROFIT_ORDER)
                self.asks[tp_order.data['ticker']][tp_order.data['take_profit']].append(tp_order)
                await self.order_manager.append_tp(tp_order)

            # Stop Loss
            if data.get('stop_loss', None):
                sl_order = _Order(data, _OrderType.TAKE_PROFIT_ORDER)
                self.asks[sl_order.data['ticker']][sl_order.data['take_profit']].append(sl_order)
                await self.order_manager.append_sl(sl_order)
                
        except Exception as e:
            print("Error placing TP SL\n", type(e), str(e))            
            print('-' * 10)
            
    
    async def handle_market_order(self, data: dict, channel: str) -> None:
        """
        Handles the creation and submission to orderbook
        for a buy order

        Args:
            data (dict)
        """
        order = _Order(data, _OrderType.MARKET_ORDER)
        result: tuple = await self.match_bid_order(order=order, ticker=order.data['ticker'])
        
        # Relaying message to user
        status_message = {
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
                    "order_id": data["order_id"]
                })
            }
        }.get(result[0])
        

        await self.publish_update_to_client(**status_message)
        
        # Insufficient liquidity, not filled or forwarded to the book
        if result[0] == 0:
            return
        
        # Sending to the order manager for reference
        await self.order_manager.append_entry(order)
        
        # Order was successfully filled
        if result[0] == 2:
            try:
                # await self.place_tp_sl(data)
                
                data["filled_price"] = result[1]
                order.order_status = OrderStatus.FILLED
                order.standing_quantity = data['quantity']
                await self.order_manager.batch_update([data])
                
                self.current_price = result[1]
                await self.add_new_price_to_db(result[1], data['ticker'], int(datetime.now().timestamp()))

                print("Order successfully filled: ", self.order_manager.retrieve_entry(data['order_id']))
                
            except InvalidAction as e:
                await self.publish_update_to_client(channel=channel, message=json.dumps({
                    'status': 'error',
                    'message': str(e),
                    'order_id': data['order_id']
                }))
                
            finally:
                return
        
        
        # Order was partially filled so we add to orderbook
        order.order_status = OrderStatus.PARTIALLY_FILLED
        await self.order_manager.batch_update([data])
        self.bids[order.data['ticker']][order.data['price']].append(order) # Adding to the orderbook
    
    
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
                    for key in list(self.asks_price_levels[ticker])
                    if key >= bid_price
                    and self.asks[ticker][key]
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
        order: _Order = None,
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
        bid_price = bid_price if bid_price else order.data["price"]
        ask_price = await self.find_ask_price_level(bid_price, ticker=ticker)
        if not ask_price:
            return (0, )

        touched_orders: list[_Order] = []
        
        for ex_order in self.asks[ticker][ask_price]:        
            # Adding the dictionary to a batch for DB update
            touched_orders.append(ex_order)
            
            # Filling order against the quantity
            remaining_quantity = order.standing_quantity - ex_order.standing_quantity
            
            if remaining_quantity >= 0:
                order.reduce_standing_quantity(ex_order.standing_quantity)
                ex_order.standing_quantity = 0

                if ex_order.order_type in [_OrderType.STOP_LOSS_ORDER, _OrderType.TAKE_PROFIT_ORDER]:
                    ex_order.order_status = OrderStatus.CLOSED
                    ex_order.data['close_price'] = ask_price
                    ex_order.data['closed_at'] = datetime.now()
                
                elif ex_order.order_type == _OrderType.CLOSE_ORDER:
                    if ex_order.standing_quantity == 0:
                        ex_order.order_status == OrderStatus.CLOSED
                        ex_order.data['close_price'] = ask_price
                        ex_order.data['closed_at'] = datetime.now()
                    else:
                        ex_order.order_status == OrderStatus.PARTIALLY_CLOSED
            else:
                ex_order.reduce_standing_quantity(order.standing_quantity)
                order.standing_quantity = 0
                
                if ex_order.order_type in [_OrderType.STOP_LOSS_ORDER, _OrderType.TAKE_PROFIT_ORDER, _OrderType.CLOSE_ORDER]:
                    ex_order.order_status = OrderStatus.PARTIALLY_CLOSED
                else:
                    ex_order.order_status = OrderStatus.PARTIALLY_FILLED
            
            if order.standing_quantity == 0:
                break
        
        for item in touched_orders:
            self.asks[ticker][ask_price].remove(item)
        
        asyncio.create_task(self.order_manager.batch_update([item.data for item in touched_orders]))    
        if order.standing_quantity == 0:
            return (2, ask_price)

        if attempts < 20:
            attempts += 1
            return await self.match_bid_order(
                ticker,
                order,
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
            order = _Order(data, _OrderType.LIMIT_ORDER)

            self.bids[data['ticker']][data['limit_price']].append(order)
            
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
        
        except (InvalidAction, DoesNotExist) as e:
            await self.publish_update_to_client(channel=channel, message=json.dumps({
                    'status': 'error',
                    'message': str(e),
                    'order_id': data['order_id']
                }))
        
    
    async def handle_close_order(self, data: dict, channel: str) -> None:
        """
        Handles the creation and submission to orderbook
        for a sell order

        Args:
            data (dict)
        """    
        orders: list[_Order] = []
        for order_id in data['order_ids']:
            orders.append(self.order_manager.retrieve_entry(order_id))
            
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
        print('Fill close order result: ', result)
        
        # Not closed
        if result[0] == 0:
            await self.publish_update_to_client(channel, {
                    "status": ConsumerStatusType.ERROR,
                    "message": "Insufficient bids to fulfill sell order",
                    "order_id": order_obj.data['order_id']
                })
            return False

        # Relaying message to user
        status_message = {
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


        # Order was successfully closed
        if result[0] == 2:
            try:
                open_price = order_obj.data.get('filled_price', None) or order_obj.data.get('price')
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
                    for key in self.bids_price_levels[ticker]
                    if key <= ask_price
                    and self.bids[ticker][key]
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
        
        touched_orders: list[_Order] = []
        
        # Fulfilling the order
        for ex_order in self.bids[ticker][bid_price]:
            print('Current Trying to fill against: ', ex_order)
            touched_orders.append(ex_order)
            
            remaining_quantity = quantity - ex_order.standing_quantity
            
            if remaining_quantity >= 0:
                ex_order.order_status = OrderStatus.FILLED
                main_order.reduce_standing_quantity(ex_order.standing_quantity)
            else:
                ex_order.order_status = OrderStatus.PARTIALLY_FILLED
                main_order.reduce_standing_quantity(quantity)
                
            quantity -= ex_order.standing_quantity
            if quantity <= 0:
                break
            
        for item in touched_orders:
            if item.order_status == OrderStatus.FILLED:
                self.bids[ticker][bid_price].remove(item)
        
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
        self.bids[data['ticker']][data['limit_price']].append(_Order(data, _OrderType.LIMIT_ORDER))
        await self.publish_update_to_client(
            channel,
            {'status': ConsumerStatusType.SUCCESS, 'message': 'Limit Order placed successfully'}
        )
        print(self.bids[data['ticker']][data['limit_price']])
    
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
