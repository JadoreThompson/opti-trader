import asyncio, json, redis
from datetime import datetime
from functools import wraps
from uuid import UUID

# FA
from fastapi import WebSocket
from pydantic import ValidationError

# SA
import redis.asyncio.connection
from sqlalchemy import insert, select, update

# Local
from db_models import Orders, Users
from exceptions import UnauthorisedError, InvalidAction
from enums import ConsumerStatusType, OrderType, OrderStatus
from models.matching_engine_models import OrderRequest
from utils.auth import verify_jwt_token_ws
from utils.connection import RedisConnection
from utils.db import get_db_session
from .config import REDIS_HOST


REDIS_CONN_POOL = redis.asyncio.connection.ConnectionPool(
    connection_class=RedisConnection, 
    max_connections=20
)
REDIS_CLIENT = redis.asyncio.client.Redis(connection_pool=REDIS_CONN_POOL, host=REDIS_HOST)


def websocket_exception_handler(func):
    """
    Handles exceptions that may occur during the websocket's
    lifespan
    :param func:
    :return:
    """
    @wraps(func)
    async def handle_exceptions(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        
        except (ValidationError, AttributeError) as e:
            await self.socket.send_text(json.dumps({
                'status': ConsumerStatusType.ERROR,
                'message': 'Invalid Schema'
            }))
        
        except (UnauthorisedError, InvalidAction) as e:
            await self.socket.send_text(json.dumps({
                'status': ConsumerStatusType.ERROR,
                'message': str(e)
            }))

        except Exception as e:
            print('WebSocket Error:')
            print(type(e), str(e))
            print('-' * 10)           
            
    return handle_exceptions


class ClientManager:
    def __init__(self, websocket: WebSocket):
        self.socket: WebSocket = websocket
        self.ticker_quotes: dict[str, float] = {'APPL': 110}
        self._balance: float =  None
    
            
    @property
    def balance(self) -> float:
        return self._balance


    @balance.setter
    def balance(self, value: float) -> None:
        if self._balance != value:
            self._balance = value
            asyncio.create_task(self.save_changes_db())
    
    
    async def save_changes_db(self) -> None:
        async with get_db_session() as session:
            await session.execute(
                update(Users)
                .where((Users.user_id == self.user.user_id))
                .values(balance=self.balance)
            )
            await session.commit()
    
            
    @websocket_exception_handler
    async def connect(self) -> None:
        await self.socket.accept()
    
    
    @websocket_exception_handler
    async def receive(self) -> None:
        message = await self.socket.receive_text()
        message = json.loads(message)
        # Verifying user
        try:
            user_id = verify_jwt_token_ws(message['token'])
        except KeyError:
            await self.socket.close(code=1014, reason='Token not provided')
            return
        
        if not await self.check_user_exists(user_id):
            raise UnauthorisedError("User doesn't exist")

        await self.socket.send_text(json.dumps({
            'status': ConsumerStatusType.SUCCESS,
            'message': 'Connected successfully'
        }))
        
        
        # Starting up functions
        await asyncio.gather(*[
            self.listen_to_prices(),
            self.handle_incoming_requests(),
            self.listen_to_order_updates(),
        ])
        

    async def check_user_exists(self, user_id: str) -> bool:
        """
        Checks if the user_id is present in the DB

        Args:
            user_id (str):

        Returns:
            bool: True - user exists. False - user doesn't exist
        """        
        try:
            async with get_db_session() as session:
                result = await session.execute(
                    select(Users)
                    .where(Users.user_id == user_id)
                )
                self.user = result.scalar()
                
                if not self.user:
                    return False
                
                self.balance = self.user.balance
                return True
        except Exception as e:
            print(type(e), str(e))
            print('-' * 10)


    async def listen_to_prices(self) -> None:
        """
        Subscribes to the prices channel for 
        all ticker prices
        """        
        
        async with REDIS_CLIENT.pubsub() as pubsub:
            await asyncio.sleep(0.1)
            await pubsub.subscribe('prices')
            
            async for message in pubsub.listen():
                if message.get('type', None) == 'message':
                    data = json.loads(message['data'].decode())
                    self.ticker_quotes[data['ticker']] = data['price']
                    
                    await self.socket.send_text(json.dumps({
                        "status": ConsumerStatusType.PRICE_UPDATE,
                        "message": data,
                    }))


    async def create_market_order_handler(self, message: OrderRequest) -> dict:
        """
        Creates order in the DB, returns the order as a (dict)
        
        Args:
            message (OrderRequest):

        Returns:
            dict: Created Order
        """        
        # current_price = self.ticker_quotes[message.market_order.ticker]
        # boundary = current_price * 0.5
        
        # if boundary >= message.limit_order.limit_price or message.limit_order.limit_price >= (boundary + current_price):
        #     await self.socket.send_text(json.dumps({
        #         'status': ConsumerStatusType.ERROR,
        #         'message': "Can't place order on specified  price"
        #     }))
        #     return
        
        temp_message = message.market_order.model_dump()
        
        take_profit_price = None
        stop_loss_price = None

        if isinstance(temp_message.get('take_profit'), dict):
            take_profit_price = temp_message['take_profit'].get('price')

        if isinstance(temp_message.get('stop_loss'), dict):
            stop_loss_price = temp_message['stop_loss'].get('price')

        if not await self.validate_tp_sl(
            take_profit_price=take_profit_price,
            stop_loss_price=stop_loss_price,
            ticker=temp_message['ticker']
        ): return
        
        
        order: dict = await self.create_order_in_db(message)
        if order:
            return order
        
    
    async def create_limit_order_handler(self, message: OrderRequest) -> dict | None:
        """
        Checks that the price beign requested is within reason, creates order

        Args:
            message (OrderRequest):

        Returns:
            dict: Order as a (dict)
            None: Price was outside of the boundary
        """        
        
        temp_message = message.limit_order.model_dump()
        
        take_profit_price = None
        stop_loss_price = None

        if isinstance(temp_message.get('take_profit'), dict):
            take_profit_price = temp_message['take_profit'].get('price')

        if isinstance(temp_message.get('stop_loss'), dict):
            stop_loss_price = temp_message['stop_loss'].get('price')

        if not await self.validate_tp_sl(
            take_profit_price=take_profit_price,
            stop_loss_price=stop_loss_price,
            ticker=temp_message.get('ticker')
        ): return
        
        
        current_price = self.ticker_quotes[message.limit_order.ticker]
        boundary = current_price * 0.5
        
        if boundary >= message.limit_order.limit_price or message.limit_order.limit_price >= (boundary + current_price):
            await self.socket.send_text(json.dumps({
                'status': ConsumerStatusType.ERROR,
                'message': "Can't place order on specified  price"
            }))
            return
        
        payload: dict = await self.create_order_in_db(message)
        if payload:
            return payload
    
    
    async def close_orders_handler(self, message: OrderRequest) -> None:
        """
        Retrieves orders and sends to the engine. It'll send to the engine 
        if the user has enough quantity to satisfy their request else it'll
        notify the user of the insufficient inventory

        Args:
            message (OrderRequest):
        """        
        order_ids: list = await self.fetch_orders(
            message.close_order.quantity,
            message.close_order.ticker,
        )
        
        if not order_ids:
            await self.socket.send_text(json.dumps({
                'status': ConsumerStatusType.ERROR,
                'message': 'Insufficient asset value'
            }))
            return
    
        payload = vars(message.close_order)
        payload.update({
            'type': message.type,
            'order_ids': order_ids,
            'user_id': str(self.user.user_id),
            'price': self.ticker_quotes.get(payload['ticker'])
        })
        
        return payload


    async def modify_order_handler(self, message: OrderRequest) -> dict:
        async with get_db_session() as session:
            result = await session.execute(
                select(Orders.order_status)
                .where(
                    (Orders.user_id == self.user.user_id)
                    & (Orders.order_id == message.modify_order.order_id)
                    & (Orders.order_status != OrderStatus.CLOSED)
                )
            )
            
            order = result.scalars().first()
        
        payload: dict = message.modify_order.model_dump()
        payload.update({'order_status': order})
        payload['order_id'] = str(payload['order_id'])
        
        if order: 
            return payload
        


    @websocket_exception_handler
    async def handle_incoming_requests(self) -> None:
        """
        Handles the different types of requests
        the user sends. Acts as the funneler
        """    
        while True:
            message = await self.socket.receive_text()
            
            try:
                message = OrderRequest(**json.loads(message))
            except ValidationError as e:                
                await self.socket.send_text(json.dumps({
                    'status': ConsumerStatusType.ERROR,
                    'message': e.errors()
                }))
                continue
            
            payload = await {
                OrderType.MARKET: self.create_market_order_handler,
                OrderType.LIMIT: self.create_limit_order_handler,
                OrderType.CLOSE: self.close_orders_handler,
                OrderType.MODIFY: self.modify_order_handler
            }.get(message.type)(message)
            
            if not isinstance(payload, dict):
                continue
            
            # Can't edit a closed order
            if payload['order_status'] == OrderStatus.CLOSED:
                await self.socket.send_text(json.dumps({
                    'status': 'error',
                    'message': 'Cannot perform actions on closed orders',
                    'order_id': payload['order_id']
                }))
                return
                    
            # Shipping off to the engine for computation
            payload.update({'type': message.type, 'user_id': str(self.user.user_id)})
            asyncio.create_task(self.send_order_to_engine(payload))
            
            
    @websocket_exception_handler
    async def validate_tp_sl(
        self, 
        ticker: str,
        take_profit_price: float = None, 
        stop_loss_price: float = None, 
    ) -> bool:
        """

        Args:
            take_profit_price (float):
            stop_loss_price (float): 
            ticker (str):

        Returns:
            bool: 
                - False:
                    - Stop loss price is greater than or equal to current market price
                    - Take Profit price is less than or equal to current market price
                - Else True
        """        
        current_price = self.ticker_quotes.get(ticker, None)
        
        if take_profit_price:
            if current_price >= take_profit_price:
                raise UnauthorisedError('Invalid TP')        
        if stop_loss_price:
            if current_price <= stop_loss_price:                
                raise UnauthorisedError('Invalid SL')        
        return True
        
    
    @websocket_exception_handler
    async def create_order_in_db(self, message: OrderRequest) -> dict:
        """
        Creates a record of the order within the databse

        Args:
            message (OrderRequest)

        Returns:
            dict: A dictionary representation of the order without the _sa_instance_state key
        """
        try:
            message_dict = message.limit_order.model_dump() if message.limit_order else message.market_order.model_dump()
            
            amount = self.ticker_quotes[message_dict['ticker']] * message_dict['quantity']
            if amount > self.user.balance:
                await self.socket.send_text(json.dumps({'status': ConsumerStatusType.ERROR, 'message': 'Insufficient balance'}))
                return
            
            self.balance -= amount
                                    
            for field in ['stop_loss', 'take_profit']:
                if isinstance(message_dict.get(field, None), dict):
                    message_dict[field] = message_dict.get(field, {}).get('price', None)
            
            message_dict['user_id'] = self.user.user_id
            message_dict['order_type'] = message.type
            message_dict['standing_quantity'] = message_dict['quantity']
            
            # Getting the price
            message_dict['price'] = message_dict.get('limit_price', None)\
                if message_dict.get('limit_price', None) else self.ticker_quotes['APPL']

            # Inserting
            async with get_db_session() as session:
                result = await session.execute(
                    insert(Orders)
                    .values(message_dict)
                    .returning(Orders)
                )
                    
                order = {
                    key: (str(value) if isinstance(value, (UUID, datetime)) else value) 
                    for key, value in vars(result.scalar()).items()
                    if key != '_sa_instance_state'
                }
                
                await session.commit()
                return order
        except InvalidAction:
            raise
    
    
    async def fetch_orders(
        self,        
        target_quantity: int, 
        ticker: str
    ) -> list:
        """
        Fetches all orders where the quantity adds up to the
        quantity being requested and the ticker is the ticker in
        question. Used by close order handler
        
        :param: quantity[int]
        :param: user_id[str]
        :param: ticker[str]
        """
        async with get_db_session() as session:
            r = await session.execute(
                select(Orders.order_id, Orders.standing_quantity)
                .where(
                    (Orders.user_id == self.user.user_id) 
                    & (Orders.ticker == ticker) 
                    & (
                        (Orders.order_status == OrderStatus.FILLED)
                        |
                        (Orders.order_status == OrderStatus.PARTIALLY_CLOSED_ACTIVE)
                    )
                )
            )
            all_orders = r.all() 
            
        order_ids = []
        for order in all_orders:
            target_quantity -= order[1]
            order_ids.append(str(order[0]))
            
            if target_quantity <= 0:                
                return order_ids
            
        return []
    
    async def send_order_to_engine(self, order: dict) -> None:
        """
        Sends the order to the matching engine

        Args:
            order (dict)
        """        
        await REDIS_CLIENT.publish(
            channel="to_order_book",
            message=json.dumps(order)
        )
        
    
    async def listen_to_order_updates(self) -> None:
        """
        Subscribes to trades_{user_id}
        and relays the messages back to the client
        """        
        async with REDIS_CLIENT.pubsub() as pubsub:
            await pubsub.subscribe(f"trades_{self.user.user_id}")
            
            async for message in pubsub.listen():
                await asyncio.sleep(0.1)
                
                if message.get('type', None) == 'message':
                    message = json.loads(message['data'])
                    await self.socket.send_text(json.dumps(message))
                    