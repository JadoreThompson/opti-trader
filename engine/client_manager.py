import asyncio, json, redis, time, logging
from datetime import datetime
from functools import wraps
from uuid import UUID
from threading import Thread
from random import randint

# FA
from starlette.websockets import WebSocketDisconnect as StarletteWebSocketDisconnect
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

# SA
import redis.asyncio.connection
from sqlalchemy import select

# Local
from db_models import Orders, Users
from exceptions import UnauthorisedError, InvalidAction
from enums import ConsumerMessageStatus, OrderType, OrderStatus
from models.models import TickerData
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
        self._initialised: bool = False
        self._active_connections: dict[str, dict[str, any]] = {}
        self._ticker_quotes: dict[str, float] = {'APPL': randint(10, 1000)}
        
        self._message_handlers = {
            OrderType.MARKET: self._market_order_handler,
            OrderType.LIMIT: self._limit_order_handler,
            OrderType.CLOSE: self._close_order_handler
        }
        
    async def _listen_to_prices(self) -> None:
        try:
            last_price = None
            while True:
                try:
                    item = QUEUE.get_nowait()
                    if isinstance(item, (float, int)):
                        if item != last_price:
                            last_price = item
                            print('^ Received queue item: ', last_price)
                            asyncio.get_running_loop().create_task(self._process_price(last_price))
                            
                        QUEUE.task_done()    
                except asyncio.queues.QueueEmpty as e:
                    pass
                except Exception as e:
                    print('listen price client manger: ', type(e), str(e))
                finally:
                    await asyncio.sleep(0.05)        
                    
        except Exception as e:
            print('Listen to prices in client manager: ', type(e), str(e))
        finally:
            await asyncio.sleep(0.05)
    
    async def _process_price(self, new_price: float | int) -> None:
        for _, details in self._active_connections.items():
            try:
                await details['socket'].send_text(json.dumps({
                    'status': ConsumerMessageStatus.PRICE_UPDATE,
                    'message': {
                        'ticker': 'APPL', 
                        'price': new_price, 
                        'time': int(datetime.now().timestamp())
                    }
                }))
            except KeyError:
                pass
            except RuntimeError as e:
                print('Client manager - process price: ', str(e))
            except Exception as e:
                print('Client manager - ', type(e), str(e))
            finally: 
                await asyncio.sleep(0.01)
                
    async def _listen_to_order_updates(self, user_id: str) -> None:
        try:
            async with REDIS_CLIENT.pubsub() as ps:
                await ps.subscribe(f'trades_{user_id}')

                while True:
                    try:
                        message = await ps.get_message(ignore_subscribe_messages=True, timeout=0.1)
                        if message:
                            if user_id in self._active_connections:
                                socket: WebSocket = self._active_connections[user_id]['socket']
                                message: str = json.dumps(json.loads(message['data']))
                                await socket.send_text(message)
                                
                    except Exception as e:
                        print('listen to order update inner: ', type(e), str(e))
                    finally:
                        await asyncio.sleep(0.1)
              
        except Exception as e:
            print('listen to order update: ', type(e), str(e))
            
    async def cleanup(self, user_id: str) -> None: 
        if user_id in self._active_connections:
            self._active_connections[user_id]['listen_order_task'].cancel()
            del self._active_connections[user_id]
        
    async def connect(self, socket: WebSocket) -> None:
        try:
            await socket.accept()
            if not self._initialised:
                asyncio.create_task(self._listen_to_prices())
                await asyncio.sleep(0.01)
                self._initialised = True
            
        except Exception as e:
            print('connect: ', type(e), str(e))
            
    async def receive_token(self, socket: WebSocket) -> bool | str:
        try:
            message = await socket.receive_text()
            user_id: str = verify_jwt_token_ws(json.loads(message)['token'])
            user: Users = await check_user_exists(user_id)

            if user.user_id in self._active_connections:
                return False
            
            self._active_connections[user_id] = {
                'socket': socket,
                'user': user,
                'listen_order_task': asyncio.create_task(self._listen_to_order_updates(user_id=user_id)),
                # 'ping_task': asyncio.create_task(self._ping())
            }

            await socket.send_text(json.dumps({
                'status': ConsumerMessageStatus.SUCCESS,
                'message': 'Successfully connected',                
            }))

            return user_id
        except (KeyError, InvalidAction):
            return False    
        except Exception as e:
            print('receive token: ', type(e), str(e))
    
    async def receive(self, socket: WebSocket, user_id: str) -> None:
        try:
            if user_id not in self._active_connections:
                raise WebSocketDisconnect
            
            message: str = await socket.receive_text()
            
            asyncio.create_task(self._message_handler(
                message=OrderRequest(**json.loads(message)), 
                user_id=user_id
            ))
            await asyncio.sleep(0.1)
            
        except ValidationError as e:
            await socket.send_text(json.dumps({
                'status': ConsumerMessageStatus.ERROR,
                'message': e.errors()
            }))
        except (TypeError, RuntimeError, StarletteWebSocketDisconnect) as e:
            raise WebSocketDisconnect
        except Exception as e:
            print('receive: ', type(e), str(e))
    
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
            QUEUE.put_nowait(order)
            
        except (InvalidAction, UnauthorisedError) as e:
            await self._active_connections[user_id]['socket'].send_text(json.dumps({
                'status': ConsumerMessageStatus.ERROR,
                'message': str(e)
            }))
        except Exception as e:
            print('message handler: ', type(e), str(e))
    
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
        except Exception as e:
            print('validate tp sl: ', type(e), str(e))
        
        
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
            print('market order handler clietn manger: ', type(e), str(e))
            
            
    async def _limit_order_handler(self, message: OrderRequest, user_id: str) -> dict:
        message_dict: dict = message.limit_order.model_dump()
        
        try:
            if not await self._validate_tp_sl(
                tp_price=message_dict.get('take_profit', {}).get('price', None) if message_dict['take_profit'] else None,
                sl_price=message_dict.get('stop_loss', {}).get('price', None) if message_dict['stop_loss'] else None,
                ticker=message_dict['ticker']
            ): 
                return
            
            current_price = self._ticker_quotes[message_dict['ticker']]
            lower_boundary = current_price * 0.5
        
            if lower_boundary >= message_dict['limit_price'] or message_dict['limit_price'] >= (lower_boundary + current_price):
                raise InvalidAction("Limit price is outside of liquidity zone")
            
            
            if await self._validate_balance(user_id, message_dict['quantity'], message_dict['ticker']):
                return await self._create_order(message_dict, OrderType.LIMIT, user_id)
            
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
    