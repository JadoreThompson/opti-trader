import asyncio
import json
import random
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from functools import wraps
from uuid import UUID
import redis

# FA
from fastapi import WebSocket
from pydantic import ValidationError

# SA
from sqlalchemy import insert, select, inspect

# Local
from db_models import Orders, Users
from exceptions import UnauthorisedError, InvalidAction
from enums import OrderType, OrderStatus
from models.matching_engine_models import OrderRequest
from utils.auth import verify_jwt_token_ws
from utils.db import get_db_session


# Redis
REDIS_CONN_POOL = redis.asyncio.connection.ConnectionPool(max_connections=20)
REDIS_CLIENT = redis.asyncio.client.Redis(connection_pool=REDIS_CONN_POOL)


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
            error = "Invalid Schema"
            await self.socket.close(code=1014, reason=error)
        
        except (UnauthorisedError, InvalidAction) as e:
            error = str(e)
            await self.socket.close(code=1014, reason=error)

        except Exception as e:
            print('WebSocket Error:')
            print(type(e), str(e))
            print('-' * 10)           
            
    return handle_exceptions


class ClientManager:
    def __init__(self, websocket: WebSocket):
        self.socket: WebSocket = websocket
        self.ticker_quotes: dict[str, float] = defaultdict(float)
        pass
    
    
    @websocket_exception_handler
    async def connect(self) -> None:
        await self.socket.accept()
    
    
    @websocket_exception_handler
    async def receive(self) -> None:
        message = await self.socket.receive_text()
        message = json.loads(message)
        
        # Verifying user
        user_id = verify_jwt_token_ws(message['token'])
        if not await self.check_user_exists(user_id):
            raise UnauthorisedError("User doesn't exist")

        await self.socket.send_text(json.dumps({
            'status': 'success',
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
            await pubsub.subscribe('prices')
            
            async for message in pubsub.listen():
                await asyncio.sleep(0.1)
                if message.get('type', None) == 'message':
                    self.ticker_quotes.update(json.loads(message['data'].decode()))


    @websocket_exception_handler
    async def handle_incoming_requests(self) -> None:
        """
        Handles the different types of requests
        the user sends. Acts as the funneler
        """    
        while True:
            message = await self.socket.receive_text()
            message = OrderRequest(**(json.loads(message)))
            additional_fields = {'type': message.type}
            
            
            if message.type == OrderType.MARKET or \
                message.type == OrderType.LIMIT:
                order: dict = await self.create_order_in_db(message)
                print(11)
            
            elif message.type == OrderType.CLOSE:
                order_id = message.close_order.order_id
                
                # while not price:
                # market_price = self.ticker_quotes.get(order['ticker'], None)
                # await asyncio.sleep(0.1)
                
                market_price = round(random.uniform(100, 150), 2)
                additional_fields['market_price'] = market_price
                order: dict = await self.retrieve_order(order_id)
                
            elif message.type == OrderType.ENTRY_PRICE_CHANGE:
                order_id = message.entry_price_change.order_id
                order: dict = await self.retrieve_order(order_id)
                
                if order['order_status'] != OrderStatus.NOT_FILLED:
                    await self.socket.send_text(json.dumps({
                        'status': 'error',
                        'message': "Can't update entry price of partially or fully filled order",
                        'order_id': order['order_id']
                    }))
                    return
                
                additional_fields['new_entry_price'] = message.entry_price_change.price
            
            elif message.type == OrderType.TAKE_PROFIT_CHANGE:
                order_id = message.take_profit_change.order_id
                additional_fields['new_take_profit_price'] = message.take_profit_change.price
                order: dict = await self.retrieve_order(order_id)
            
            elif message.type == OrderType.STOP_LOSS_CHANGE:
                order_id = message.stop_loss_change.order_id
                additional_fields['new_stop_loss_price'] = message.stop_loss_change.price
                order: dict = await self.retrieve_order(order_id)
            
            # Can't edit a closed order
            if order['order_status'] == OrderStatus.CLOSED:
                await self.socket.send_text(json.dumps({
                    'status': 'error',
                    'message': 'Order already closed',
                    'order_id': order['order_id']
                }))
                return
            
            
            # Shipping off to the engine for computation
            order.update(additional_fields)
            asyncio.create_task(self.send_order_to_engine(order))
            
    
    async def create_order_in_db(self, message: OrderRequest) -> dict:
        """
        Creates a record of the order within the databse

        Args:
            message (OrderRequest)

        Returns:
            dict: A dictionary representation of the order without the _sa_instance_state key
        """
        try:
            message_dict = message.limit_order if message.limit_order else message.market_order
            message_dict = message_dict.model_dump()
            
            while message_dict['ticker'] not in self.ticker_quotes:
                await asyncio.sleep(0.1)
            
            if self.ticker_quotes[message_dict['ticker']] * message_dict['quantity'] > self.user.balance:
                raise InvalidAction("Insufficient balance")
                        
            for field in ['stop_loss', 'take_profit']:
                if isinstance(message_dict.get(field, None), dict):
                    message_dict[field] = message_dict.get(field, {}).get('price', None)
            
            message_dict['user_id'] = self.user.user_id
            message_dict['order_type'] = message.type
            
            # Getting the price
            message_dict['price'] = message_dict.get('limit_price', None)\
                if message_dict.get('limit_price', None) else 110

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
    
    async def retrieve_order(self, order_id: str | UUID) -> dict:
        """
        Retrieves an order within the DB with the order_id

        Args:
            order_id (str | UUID)

        Returns:
            dict: A dictionary representation of the order without the _sa_instance_state key
        """        
        try:
            print("Order ID: ", type(order_id))
            async with get_db_session() as session:
                result = await session.execute(
                    select(Orders)
                    .where(Orders.order_id == order_id)
                )
                                
                return {
                    key: (str(value) if isinstance(value, (UUID, datetime)) else value) 
                    for key, value in vars(result.scalar()).items()
                    if key != '_sa_instance_state'
                }
        except Exception as e:
            print("Retrieve order\n", type(e), str(e))
            print("-" * 10)
    
    
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
                    await self.socket.send_bytes(json.dumps(message))
                    