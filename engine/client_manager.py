import asyncio, json, redis, time, logging
from datetime import datetime
from functools import wraps
from uuid import UUID
from threading import Thread
# FA
from fastapi import WebSocket
from pydantic import ValidationError

# SA
import redis.asyncio.connection
from sqlalchemy import select

# Local
from db_models import Orders, Users
from exceptions import UnauthorisedError, InvalidAction
from enums import ConsumerMessageStatus, OrderType, OrderStatus
from models.socket_models import OrderRequest
from utils.auth import verify_jwt_token_ws
from utils.connection import RedisConnection
from utils.db import get_db_session, check_user_exists
from .config import QUEUE, REDIS_HOST


logger = logging.getLogger(__name__)

REDIS_CONN_POOL = redis.asyncio.connection.ConnectionPool(
    connection_class=RedisConnection, 
    max_connections=20
)
REDIS_CLIENT = redis.asyncio.client.Redis(connection_pool=REDIS_CONN_POOL, host=REDIS_HOST)


class ClientManager:
    def __init__(self) -> None:
        self.initialised: bool = False
        self._active_connections: dict[str, dict[str, any]] = {}
        self._ticker_quotes: dict[str, float] = {'APPL': 100.0}
        
        self._message_handlers = {
            OrderType.MARKET: self._market_order_handler,
            OrderType.LIMIT: self._limit_order_handler,
            OrderType.CLOSE: self._close_order_handler
        }
    
        asyncio.run(self.startup())
        
    
    def _startup_handler(self) -> None:
        asyncio.run(self._listen_to_prices())
    
    
    async def startup(self) -> None:
        if not self.initialised:
            self._price_listener_thread: Thread = Thread(target=self._startup_handler, daemon=True)
            self._price_listener_thread.start()
            
            await asyncio.sleep(0.5)
            self.initialised = True
            
            print('Initialised')
        else:
            print('Already initialised')
    
    
    async def _listen_to_prices(self) -> None:
        try:
            self._pubsub = REDIS_CLIENT.pubsub()
            await self._pubsub.subscribe('prices')
                
            while True:
                message = await self._pubsub.get_message(ignore_subscribe_messages=True)
                if message:
                    if message.get('type', None) == 'message':
                        asyncio.create_task(self._process_price(message['data']))
        except Exception as e:
            print(str(e))
    
    
    async def _process_price(self, payload: bytes) -> None:
        payload = json.loads(payload)
        
        for _, details in self._active_connections.items():
            try:
                await details['socket'].send_text(json.dumps({
                    'status': ConsumerMessageStatus.PRICE_UPDATE,
                    'message': payload
                }))
            except KeyError:
                pass
            finally: 
                continue
            
    
    async def _listen_to_order_updates(self, user_id: str) -> None:
        await self._pubsub.subscribe(f'trades_{user_id}')
        while True:
            message = await self._pubsub.get_message(ignore_subscribe_messages=True)
            if message:
                if message.get('type', None) == 'message':
                    asyncio.create_task(self._process_order_update(user_id=user_id, payload=message['data']))
            await asyncio.sleep(0.1)
    
    
    async def _process_order_update(self, user_id: str, payload: bytes) -> None:        
        await self._active_connections[user_id]['socket'].send_text(json.dumps(json.loads(payload)))


    async def cleanup(self, user_id: str) -> None: 
        if user_id in self._active_connections:
            del self._active_connections[user_id]
        
    
    async def connect(self, socket: WebSocket) -> None:
        await socket.accept()
    
    
    async def receive_token(self, socket: WebSocket) -> bool:
        message = await socket.receive_text()
        message = json.loads(message)
        
        try:
            user_id: str = verify_jwt_token_ws(message['token'])
            user: Users = await check_user_exists(user_id)

            if user.user_id in self._active_connections:
                return False
            
            self._active_connections[user_id] = {
                'socket': socket,
                'user': user,
            }
            
            await socket.send_text(json.dumps({
                'status': ConsumerMessageStatus.SUCCESS,
                'message': 'Successfully connected'
            }))
            
            return user_id
        except (KeyError, InvalidAction):
            return False
        
    
    async def receive(self, socket: WebSocket, user_id: str):
        try:
            message: str = await socket.receive_text()
            asyncio.create_task(self._message_handler(
                message=OrderRequest(**json.loads(message)), 
                user_id=user_id
            ))
        except ValidationError as e:
            await socket.send_text(json.dumps({
                'status': ConsumerMessageStatus.ERROR,
                'message': e.errors()
            }))
        except Exception as e:
            logger.error(str(e))
    
    
    async def _message_handler(self, message: OrderRequest, user_id: str) -> None:
        try:
            order: dict = await self._message_handlers[message.type]\
            (
                message=message,
                user_id=user_id
            )

            
            if 'order_status' in order:
                if order['order_status'] == OrderStatus.CLOSED:
                    raise InvalidAction("Cannot perform operations on closed orders")
            
            order.update({'type': message.type, 'user_id': user_id})
            # await QUEUE.put(order)
            
        except (InvalidAction, UnauthorisedError) as e:
            await self._active_connections[user_id]['socket'].send_text(json.dumps({
                'status': ConsumerMessageStatus.ERROR,
                'message': str(e)
            }))
    
    
    async def _validate_tp_sl(self, ticker: str, tp_price: float, sl_price: float) -> bool:
        current_price = self._ticker_quotes.get(ticker, None)

        try:
            if tp_price:
                if current_price >= tp_price:
                    raise UnauthorisedError('Invalid TP')        
            if sl_price:
                if current_price <= sl_price:                
                    raise UnauthorisedError('Invalid SL')
            return True
        except TypeError:
            raise InvalidAction("Ticker not supported")
        
        
    async def _validate_balance(self, user_id: str, quantity: int, ticker: str) -> bool:
        user: Users = self._active_connections[user_id]['user']
        purchase_amount: float = self._ticker_quotes[ticker] * quantity
        
        if purchase_amount > user.balance:
            raise InvalidAction("Insufficient balance")
        
        user.balance -= purchase_amount
        return True
        
    
    async def _create_order(self, data: dict, order_type: OrderType, user_id: str) -> dict:
        for field in ['stop_loss', 'take_profit']:
            if isinstance(data.get(field, None), dict):
                data[field] = data.get(field, {}).get('price', None)
        
        if order_type == OrderType.MARKET:
            data['price'] = self._ticker_quotes[data['ticker']]
        
        data['user_id'] = user_id
        data['order_type'] = order_type

        async with get_db_session() as session:
            order = Orders(**data)
            session.add(order)
            await session.commit()
            
        return {
            key: (str(value) if isinstance(value, (UUID, datetime)) else value) 
            for key, value in vars(order).items()
            if key != '_sa_instance_state'
        }
        
    
    async def _market_order_handler(self, message: OrderRequest, user_id: str)-> dict:
        message_dict: dict = message.market_order.model_dump()
                
        try:
            if not await self._validate_tp_sl(
                tp_price=message_dict.get('take_profit', {}).get('price', None) if message_dict['take_profit'] else None,
                sl_price=message_dict.get('stop_loss', {}).get('price', None) if message_dict['stop_loss'] else None,
                ticker=message_dict['ticker']
            ): 
                return
            
            if await self._validate_balance(user_id, message_dict['quantity'], message_dict['ticker']):
                return await self._create_order(message_dict, OrderType.MARKET, user_id)
            
        except (InvalidAction, UnauthorisedError):
            raise
        except Exception as e:
            print(type(e), str(e))
            
            
    async def _limit_order_handler(self, message: OrderRequest, user_id: str) -> dict:
        message_dict: dict = message.limit_order.model_dump()
        
        try:
            if not await self._validate_tp_sl(
                tp_price=message_dict.get('take_profit', {}).get('price', None) if message_dict['take_profit'] else None,
                sl_price=message_dict.get('stop_loss', {}).get('price', None) if message_dict['stop_loss'] else None,
                ticker=message_dict['ticker']
            ): 
                return
            
            current_price = self._ticker_quotes[message.limit_order.ticker]
            boundary = current_price * 0.5
        
            if boundary >= message_dict['limit_price'] or message_dict['limit_price'] >= (boundary + current_price):
                raise InvalidAction("Limit price is outside of liquidity zone")
            
            
            if await self._validate_balance(user_id, message_dict['quantity'], message_dict['ticker']):
                return await self._create_order(message_dict, OrderType.MARKET, user_id)
            
        except (InvalidAction, UnauthorisedError):
            raise
        
        
    async def _close_order_handler(self, message: OrderRequest, user_id: str) -> dict:
        message_dict: dict = message.close_order.model_dump()

        # Checking if user has enough assets to perform action
        async with get_db_session() as session:
            r = await session.execute(
                select(Orders.order_id, Orders.standing_quantity)
                .where(
                    (Orders.user_id == user_id) 
                    & (Orders.ticker == message_dict['ticker']) 
                    & (
                        (Orders.order_status == OrderStatus.FILLED)
                        |
                        (Orders.order_status == OrderStatus.PARTIALLY_CLOSED_ACTIVE)
                    )
                )
            )
            
            all_orders = r.all() 
            
        if not all_orders:
            raise InvalidAction("Insufficient assets to perform action")
            
        target_quantity = message_dict['quantity']

        # Gathering valid order ids        
        order_ids = []
        
        for order in all_orders:
            target_quantity -= order[1]
            order_ids.append(str(order[0]))
        
        
        message_dict.update({'order_ids': order_ids, 'price': self._ticker_quotes[message_dict['ticker']]})
        return message_dict
    
    
    async def _modify_order_handler(self, message: OrderRequest, user_id: str) -> dict:
        message_dict = message.modify_order.model_dump()
        
        async with get_db_session() as session:
            result = await session.execute(
                select(Orders.order_status)
                .where(
                    (Orders.user_id == user_id)
                    & (Orders.order_id == message_dict['order_id'])
                    & (Orders.order_status != OrderStatus.CLOSED)
                )
            )
            
            order_status = result.scalars().first()
        
        if not order_status:
            raise InvalidAction
                
        message_dict.update({
            'order_status': order_status, 
            'order_id': str(message_dict['order_id'])
        })
        return message_dict
    