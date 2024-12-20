import asyncio
import asyncpg
import json
import logging
import redis
import queue

from datetime import datetime
from uuid import UUID
from random import randint
from multiprocessing import Queue

# FA
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect as StarletteWebSocketDisconnect

# SA
import redis.asyncio.connection
from sqlalchemy import select

# Local
from db_models import Orders, UserWatchlist, Users
from config import REDIS_HOST, REDIS_CONN_POOL
from exceptions import UnauthorisedError, InvalidAction
from enums import ConsumerMessageStatus, OrderType, OrderStatus
from models.socket_models import Request
from utils.auth import verify_jwt_token_ws
from utils.db import get_db_session, check_user_exists
from utils.tasks import send_copy_trade_email


logger = logging.getLogger(__name__)
REDIS_CLIENT = redis.asyncio.client.Redis(connection_pool=REDIS_CONN_POOL, host=REDIS_HOST)


class ClientManager:
    _initialised: bool = False
    _active_connections: dict[str, dict[str, any]] = {}
    _ticker_quotes: dict[str, float] = {'APPL': randint(10, 1000)}
    
    def __init__(self, queue: Queue=None) -> None:    
        self.order_queue = queue
        self.price_queue = None
        self._message_handlers = {
            OrderType.MARKET: self._market_order_handler,
            OrderType.LIMIT: self._limit_order_handler,
            OrderType.CLOSE: self._close_order_handler,
            OrderType.MODIFY: self._modify_order_handler,
        }
        
    async def _listen_to_prices(self) -> None:
        """Listens to prices from the Orderbook instances for sendout"""        
        try:
            while True:
                try:
                    item = self.price_queue.get_nowait()
                    if isinstance(item, tuple):
                        ticker, price = item
                        if price == self._ticker_quotes[ticker]:
                            continue
                        
                        self._ticker_quotes[ticker] = price
                        asyncio.get_running_loop().create_task(self._process_price(price, ticker))
                except (asyncio.queues.QueueEmpty, queue.Empty) as e:
                    pass
                except Exception as e:
                    logger.error(f'Inner exc >> {type(e)} - {str(e)}')
                await asyncio.sleep(0.001)        
                    
        except Exception as e:
            logger.error(f'Outer exc >> {type(e)} - {str(e)}')
        finally:
            await asyncio.sleep(0.05)
    
    async def _process_price(self, price: float | int, ticker: str) -> None:
        for _, details in self._active_connections.copy().items():
            try:
                await details['socket'].send_text(json.dumps({
                    'status': ConsumerMessageStatus.PRICE_UPDATE,
                    'message': {
                        'ticker': ticker, 
                        'price': price, 
                        'time': int(datetime.now().timestamp()),
                    },
                }))
            except (KeyError, RuntimeError, StarletteWebSocketDisconnect):
                pass
            except Exception as e:
                logger.error(f'{type(e)} - {str(e)}')
            
            await asyncio.sleep(0.01)
                
    async def _listen_to_order_updates(self, user_id: str) -> None:
        try:
            channel = f'trades_{user_id}'
            await asyncio.sleep(0.5)
            async with REDIS_CLIENT.pubsub() as ps:
                await ps.subscribe(channel)

                while True:
                    try:
                        message = await ps.get_message(ignore_subscribe_messages=True, timeout=0.1)
                        if message:
                            if user_id in self._active_connections:
                                socket: WebSocket = self._active_connections[user_id]['socket']
                                message: str = json.loads(message['data'])
                                await socket.send_text(json.dumps(message))
                                asyncio.create_task(self._send_copy_trade_alerts(message=message, user_id=user_id))
                                await asyncio.sleep(0.1)
                    except StarletteWebSocketDisconnect:
                        await ps.unsubscribe(channel)
                        break
                    except Exception as e:
                        logger.error(f'Inner exc >> {type(e)} - {str(e)}')
                    finally:
                        await asyncio.sleep(0.1)
              
        except Exception as e:
            logger.error(f'Outer exc >> {type(e)} - {str(e)}')
            
    async def _send_copy_trade_alerts(self, message: dict, user_id: str) -> None:
        """
        Sends alerts to all subscribed users
        Args:
            message (dict): _description_
            user_id (str): _description_
        """       
        try: 
            if message['status'] == ConsumerMessageStatus.SUCCESS:        
                internal = message.get('internal', None)
                
                if internal not in [OrderType.MARKET, OrderType.LIMIT]:
                    return
                
                await asyncio.gather(*[
                    self._copy_trade_email_handler(user_id, internal, message),
                    self._copy_trader_socket_handler(internal, user_id, message)
                ])
        except Exception as e:
            logger.error(f'Outer exc >> {type(e)} - {str(e)}')
            
    async def _copy_trade_email_handler(self, user_id, order_type: OrderType, message: dict) -> None:
        """Finds all watchers for the user_id and calls the corresponding celery task"""
        componenets = [[], None]
        
        query = \
            select(UserWatchlist.watcher)\
            .where(UserWatchlist.master == user_id)
    
        if order_type == OrderType.MARKET:
            query = query.where(UserWatchlist.market_orders == True)
        elif order_type == OrderType.LIMIT:
            query = query.where(UserWatchlist.limit_orders == True)
        
        try:
            async with get_db_session() as session:        
                result = await session.execute(
                    select(Users.email)
                    .where(Users.user_id.in_(query))
                )
                componenets[0] = [item[0] for item in result.all()]
                
                if not componenets[0]:
                    return
                
                result = await session.execute(
                    select(Users.username)
                    .where(Users.user_id == user_id)
                )
                componenets[1] = result.first()[0]
            
            
            send_copy_trade_email.delay(
                componenets[0], 
                componenets[1], 
                **message['details']
            )
            
        except Exception as e:
            logger.error('{} - {}'.format(type(e), str(e)))
            
    async def _copy_trader_socket_handler(self, order_type: str, user_id: str, message: dict) -> None:
        """Sends out socket message to all users with user_id as master"""
        query = select(UserWatchlist.watcher).where(UserWatchlist.master == user_id)
                
        if order_type == OrderType.LIMIT:
            query = query.where(UserWatchlist.limit_orders == True)
        elif order_type == OrderType.MARKET:
            query = query.where(UserWatchlist.market_orders == True)
        
        async with get_db_session() as session:
            r = await session.execute(query)
            watchlist = r.all()
            
            if not watchlist:
                return                    
        
        for user in watchlist:
            try:
                user = str(user)
                await self._active_connections[user]['socket'].send_text(json.dumps({
                    'status': ConsumerMessageStatus.NOTIFICATION,
                    'message': f'{self._active_connections[user]['user'].username} opened an order at {message['details']['filled_price']}'
                }))
            except (KeyError, StarletteWebSocketDisconnect, RuntimeError) as e:
                continue
            except Exception as e:
                logger.error(f'Inner exc >> {type(e)} - {str(e)}')
            
    def cleanup(self, user_id: str) -> None: 
        if user_id in self._active_connections:
            try:
                self._active_connections[user_id]['listen_order_task'].cancel()
                del self._active_connections[user_id]
            except Exception as e:
                logger.error(f'{type(e)} - {str(e)}')
        
    async def connect(self, socket: WebSocket) -> None:
        try:
            await socket.accept()
            if not self._initialised:
                asyncio.create_task(self._listen_to_prices())
                await asyncio.sleep(0.01)
                self._initialised = True
            
        except Exception as e:
            logger.error(f'{type(e)} - {str(e)}')
            
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
            }

            await socket.send_text(json.dumps({
                'status': ConsumerMessageStatus.SUCCESS,
                'message': 'Successfully connected',                
            }))

            return user_id
        except (KeyError, InvalidAction):
            return False
        except StarletteWebSocketDisconnect:
            raise
        except Exception as e:
            logger.error(f'{type(e)} - {str(e)}')
    
    async def receive(self, socket: WebSocket, user_id: str) -> None:
        try:
            if user_id not in self._active_connections:
                raise WebSocketDisconnect
            
            message: str = await socket.receive_text()
            
            asyncio.create_task(self._message_handler(
                message=Request(**json.loads(message)), 
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
            logger.error(f'{type(e)} - {str(e)}')
    
    async def _message_handler(self, message: Request, user_id: str) -> None:
        try:
            order: dict = await self._message_handlers[message.type]\
                (message=message, user_id=user_id)
            
            if order:
                if 'order_status' in order:
                    if order['order_status'] == OrderStatus.CLOSED:
                        raise InvalidAction("Cannot perform operations on closed orders")

                order.update({'type': message.type, 'user_id': user_id})
                self.order_queue.put_nowait(order)
                logger.info('{mtype} succesfully sent'.format(mtype=message.type))
                
        except (InvalidAction, UnauthorisedError) as e:
                await self._active_connections[user_id]['socket'].send_text(json.dumps({
                    'status': ConsumerMessageStatus.ERROR,
                    'message': str(e)
                }))
        except Exception as e:
            logger.error(f'{type(e)} - {str(e)}')
    
    def _validate_tp_sl(self, ticker: str, tp_price: float, sl_price: float) -> bool:
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
            logger.error(f'{type(e)} - {str(e)}')
        
        
    def _validate_balance(self, user_id: str, quantity: int, ticker: str) -> bool:
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
        
    async def _market_order_handler(self, message: Request, user_id: str)-> dict:
        message_dict: dict = message.market_order.model_dump()
                
        try:
            self._validate_tp_sl(
                tp_price=message_dict.get('take_profit', {}).get('price', None) if message_dict['take_profit'] else None,
                sl_price=message_dict.get('stop_loss', {}).get('price', None) if message_dict['stop_loss'] else None,
                ticker=message_dict['ticker']
            )
            self._validate_balance(user_id, message_dict['quantity'], message_dict['ticker'])
            return await self._create_order(message_dict, OrderType.MARKET, user_id)
        except (InvalidAction, UnauthorisedError) as e:
            raise
        except asyncpg.exceptions.TooManyConnectionsError:
            logger.info('Too many db connections')
        except Exception as e:
            logger.error(f'{type(e)} - {str(e)}')
            
            
    async def _limit_order_handler(self, message: Request, user_id: str) -> dict:
        message_dict: dict = message.limit_order.model_dump()
        
        try:
            self._validate_tp_sl(
                tp_price=message_dict.get('take_profit', {}).get('price', None) if message_dict['take_profit'] else None,
                sl_price=message_dict.get('stop_loss', {}).get('price', None) if message_dict['stop_loss'] else None,
                ticker=message_dict['ticker']
            )
            
            current_price = self._ticker_quotes[message_dict['ticker']]
            lower_boundary = current_price * 0.5
        
            if lower_boundary >= message_dict['limit_price'] or message_dict['limit_price'] >= (lower_boundary + current_price):
                raise InvalidAction("Limit price is outside of liquidity zone")
            
            
            self._validate_balance(user_id, message_dict['quantity'], message_dict['ticker'])
            return await self._create_order(message_dict, OrderType.LIMIT, user_id)
            
        except (InvalidAction, UnauthorisedError):
            raise
        except asyncpg.exceptions.TooManyConnectionsError:
            pass
        except Exception as e:
            logger.error('{} - {}'.format(type(e), str(e)))
        
        
    async def _close_order_handler(self, message: Request, user_id: str) -> dict:
        message_dict: dict = message.close_order.model_dump()

        # Checking if user has enough assets to perform action
        async with get_db_session() as session:
            r = await session.execute(
                select(Orders.order_id, Orders.standing_quantity)
                .where(
                    (Orders.user_id == user_id) 
                    & (Orders.ticker == message_dict['ticker']) 
                    & (
                        (Orders.order_status == OrderStatus.FILLED) |
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
    
    
    async def _modify_order_handler(self, message: Request, user_id: str) -> dict:
        message_dict = message.modify_order.model_dump()
        
        async with get_db_session() as session:
            result = await session.execute(
                select(Orders.order_status, Orders.ticker)
                .where(
                    (Orders.user_id == user_id)
                    & (Orders.order_id == message_dict['order_id'])
                    & (Orders.order_status != OrderStatus.CLOSED)
                )
            )
            
            order_details = result.first()
        
        if not order_details:
            raise InvalidAction
                
        message_dict.update({
            'order_status': order_details[0], 
            'order_id': str(message_dict['order_id']),
            'ticker': order_details[1],
        })
        return message_dict
    