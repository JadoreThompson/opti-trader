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
from enums import OrderType, OrderStatus
from models import OrderRequest
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
        
        except ValidationError as e:
            print(type(e), str(e))
            print('-' * 10)
            await self.socket.close(code=1014, reason="Invalid Schema")
        
        except AttributeError as e:
            print(type(e), str(e))
            print('-' * 10)
            await self.socket.close(code=1014, reason='Invalid Schema')    
            
        except Exception as e:
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
        if not await self.check_user_exists(message["user_id"]):
            await self.socket.close(code=1008, reason="User doesn't exist")
            raise Exception("Websocket closed")

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
        async with get_db_session() as session:
            result = await session.execute(
                select(Users)
                .where(Users.user_id == user_id)
            )
            if result.scalar():
                self.user_id = user_id
                return True
            return False
        
        
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
            
            elif message.type == OrderType.CLOSE:
                order_id = message.close_order.order_id
                
                # while not price:
                # market_price = self.ticker_quotes.get(order['ticker'], None)
                # await asyncio.sleep(0.1)
                
                market_price = round(random.uniform(100, 150), 2)
                additional_fields['market_price'] = market_price
                order: dict = await self.retrieve_order(order_id)
            
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

        Raises:
            Exception: _description_

        Returns:
            dict: A dictionary representation of the order without the _sa_instance_state key
        """        
        try:
            message_dict = message.limit_order if message.limit_order else message.market_order
            message_dict = message_dict.model_dump()
            
            message_dict['stop_loss'] = message_dict.get('stop_loss', {}).get('price', None)
            message_dict['take_profit'] = message_dict.get('take_profit', {}).get('price', None)
            message_dict['user_id'] = self.user_id
            message_dict['order_type'] = message.type
            message_dict['price'] = message_dict.get('limit_price', None)\
                if message_dict.get('limit_price', None) else round(random.uniform(100, 150), 2)
    
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
        except Exception as e:
            print("[CREATE ORDER IN DB][ERROR] >> ", type(e), str(e))
            raise Exception
    
    
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
            await pubsub.subscribe(f"trades_{self.user_id}")
            
            async for message in pubsub.listen():
                await asyncio.sleep(0.1)
                
                if message.get('type', None) == 'message':
                    await self.socket.send_text(message['data'])