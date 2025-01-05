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
from fastapi import (
    WebSocket, 
    WebSocketDisconnect
)
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect as StarletteWebSocketDisconnect

# SA
import redis.asyncio.connection
from sqlalchemy import select

# Local
from db_models import (
    DBOrder, 
    UserWatchlist, 
    Users
)
from config import (
    REDIS_HOST, 
    ASYNC_REDIS_CONN_POOL
)
from exceptions import (
    UnauthorisedError, 
    InvalidAction
)
from enums import (
    MarketType,
    PubSubCategory, 
    OrderType, 
    OrderStatus
)
from models.socket_models import (
    BasePubSubMessage,
    CloseOrder,
    FuturesContractWrite,
    ModifyOrder, 
    Request,
    SpotOrderWrite,
    TempBaseOrder
)
from utils.auth import (
    verify_jwt_token_ws
)
from utils.db import (
    get_db_session, 
    check_user_exists
)
from utils.tasks import (
    send_copy_trade_email
)


logger = logging.getLogger(__name__)
REDIS_CLIENT = redis.asyncio.client.Redis(
    connection_pool=ASYNC_REDIS_CONN_POOL, 
    host=REDIS_HOST
)


class ClientManager:
    def __init__(self, spot_queue: Queue=None, futures_queue: Queue=None) -> None:    
        self.spot_queue = spot_queue
        self.futures_queue = futures_queue
        self.price_queue = None
        self._initialised: bool = False
        self._active_connections: dict[str, dict[str, any]] = {}
        self._ticker_quotes: dict[str, float] = {'APPL': 300}  
        self._message_handlers = {
            OrderType.MARKET: self._handle_new_order,
            OrderType.LIMIT: self._handle_new_order,
            OrderType.CLOSE: self._handle_close_order,
            OrderType.MODIFY: self._modify_order_handler,
        }
    
    async def _send_update_all(self, message: dict, category: PubSubCategory) -> None:
        for _, details in self._active_connections.copy().items():
            try:
                await details['socket'].send_text(json.dumps(
                    BasePubSubMessage(
                        category=category,
                        details=message
                    ).model_dump()
                ))
            except (KeyError, RuntimeError, StarletteWebSocketDisconnect):
                pass
            except Exception as e:
                logger.error(f'{type(e)} - {str(e)}')
            
            await asyncio.sleep(0.01)
        
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
                        asyncio.get_running_loop().create_task(self._send_update_all(
                                {
                                    'ticker': ticker,
                                    'price': price,
                                    'time': int(datetime.now().timestamp())
                                },
                                PubSubCategory.PRICE_UPDATE,
                            )
                        )
                except (asyncio.queues.QueueEmpty, queue.Empty) as e:
                    pass
                except Exception as e:
                    logger.error(f'Inner exc >> {type(e)} - {str(e)}')
                await asyncio.sleep(0.001)        
                    
        except Exception as e:
            logger.error(f'Outer exc >> {type(e)} - {str(e)}')
        finally:
            await asyncio.sleep(0.05)
            
    async def _listen_to_dom(self) -> None:
        try:
            async with REDIS_CLIENT.pubsub() as ps:
                await ps.subscribe('dom')
                while True:
                    try:
                        msg = await ps.get_message(ignore_subscribe_messages=True)
                        if msg:
                            msg = json.loads(msg['data'])
                            asyncio.get_running_loop().create_task(
                                self._send_update_all(
                                    msg['details'], 
                                    PubSubCategory.DOM_UPDATE
                                )
                            )
                    except Exception as e:
                        logger.error('Inner {} - {}'.format(type(e), str(e)))
        except Exception as e:
            logger.error('Outer {} - {}'.format(type(e), str(e)))
                
    async def _listen_to_order_updates(self, user_id: str) -> None:
        try:
            channel = f'trades_{user_id}'
            await asyncio.sleep(0.5)
            async with REDIS_CLIENT.pubsub() as ps:
                await ps.subscribe(channel)

                while True:
                    try:
                        msg = await ps.get_message(ignore_subscribe_messages=True, timeout=0.1)
                        if msg:
                            if user_id in self._active_connections:
                                msg = json.loads(msg['data'])
                                
                                await self._active_connections[user_id]['socket'].send_text(json.dumps(msg))
                                asyncio.create_task(self._send_copy_trade_alerts(
                                    message=msg, 
                                    user_id=user_id
                                ))

                    except StarletteWebSocketDisconnect:
                        await ps.unsubscribe(channel)
                        break
                    except Exception as e:
                        logger.error(f'Inner exc >> {type(e)} - {str(e)}')
                    
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
            if message['category'] == PubSubCategory.SUCCESS:        
                order_type = message['details'].get('order_type', None)
                
                if order_type not in [OrderType.MARKET, OrderType.LIMIT]:
                    return
                
                await asyncio.gather(*[
                    self._copy_trade_email_handler(user_id, order_type, message),
                    self._copy_trader_socket_handler(order_type, user_id, message)
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
        query = \
            select(UserWatchlist.watcher) \
            .where(UserWatchlist.master == user_id)
                
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
                user = str(user[0])
                await self._active_connections[user]['socket'].send_text(json.dumps(
                    BasePubSubMessage(
                        category=PubSubCategory.NOTIFICATION,
                        message=f'{self._active_connections[user]['user'].username} opened an order at {message['details']['filled_price']}'
                    ).model_dump()
                ))
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
                asyncio.create_task(self._listen_to_dom())
                await asyncio.sleep(0.01)
                self._initialised = True
            
        except Exception as e:
            logger.error(f'{type(e)} - {str(e)}')
            
    async def receive_token(self, socket: WebSocket) -> str:
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

            await socket.send_text(json.dumps(
                BasePubSubMessage(
                    category=PubSubCategory.SUCCESS,
                    message="Successfully connected"
                ).model_dump()
            ))

            return user_id
        except (KeyError, InvalidAction):
            return ''
        except StarletteWebSocketDisconnect:
            raise
        except Exception as e:
            logger.error(f'{type(e)} - {str(e)}')
    
    async def receive(self, socket: WebSocket, user_id: str) -> None:
        try:
            if user_id not in self._active_connections:
                raise WebSocketDisconnect
            
            og_message: str = await socket.receive_text()
            og_message = json.loads(og_message)
            
            if og_message['market_type'] == MarketType.FUTURES:
                message = FuturesContractWrite(**og_message)
            else:
                message = {
                    OrderType.MARKET: TempBaseOrder,
                    OrderType.LIMIT: TempBaseOrder,
                    OrderType.CLOSE: CloseOrder,    
                    OrderType.MODIFY: ModifyOrder,
                }[og_message['type']](**og_message)
                
            asyncio.create_task(self._message_handler(
                message=message, 
                user_id=user_id
            ))
            
        except ValidationError as e:
            await socket.send_text(json.dumps(
                BasePubSubMessage(
                    category=PubSubCategory.ERROR,
                    message=str(e)
                ).model_dump()
            ))
        except (TypeError, RuntimeError, StarletteWebSocketDisconnect) as e:
            raise WebSocketDisconnect
        except Exception as e:
            logger.error(f'{type(e)} - {str(e)}')
    
    async def _message_handler(self, message, user_id: str) -> None:
        try:
            order: dict = await self._message_handlers[message.type]\
                (message=message, user_id=user_id)
            
            if order:
                if 'order_status' in order:
                    if order['order_status'] == OrderStatus.CLOSED:
                        raise InvalidAction("Cannot perform operations on closed orders")

                order.update({'type': message.type, 'user_id': user_id})
                
                if message.market_type == MarketType.SPOT:
                    self.spot_queue.put_nowait(order)
                else:
                    self.futures_queue.put_nowait(order)
                
                logger.info('{} succesfully sent to {} engine'.format(message.type, message.market_type))
                
        except (InvalidAction, UnauthorisedError, ValidationError) as e:
                await self._active_connections[user_id]['socket'].send_text(json.dumps(
                    BasePubSubMessage(
                        category=PubSubCategory.ERROR,
                        message=str(e)
                    ).model_dump()
                ))
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
    
    async def _create_order(self, order: TempBaseOrder, user_id: str):
        """Persist order"""
        data = order.model_dump()
        data['order_type'] = data.pop('type')
        data['user_id'] = user_id
        
        data['order_type'] = \
            OrderType.LIMIT if data['limit_price'] is not None \
            else OrderType.MARKET
                    
        if order.limit_price is None:
            data['price'] = self._ticker_quotes[data['ticker']]
        
        async with get_db_session() as sess:
            order = DBOrder(**data)
            sess.add(order)
            await sess.commit()
        
        return {
            key: (str(value) if isinstance(value, (UUID, datetime)) else value) 
            for key, value in vars(order).items()
            if key != '_sa_instance_state'
        }
            
    async def _handle_new_order(self, message: TempBaseOrder, user_id: str,) -> dict:
        try:
            self._validate_tp_sl(
                tp_price=message.take_profit,
                sl_price=message.stop_loss,
                ticker=message.ticker
            )
            self._validate_balance(user_id, message.quantity, message.ticker)
            return await self._create_order(message, user_id)
        except (InvalidAction, UnauthorisedError) as e:
            raise
        except Exception as e:
            logger.error('{} - {}'.format(type(e), str(e)))
    
    async def _handle_close_order(self, message: CloseOrder, user_id: str) -> dict:
        async with get_db_session() as session:
            r = await session.execute(
                select(DBOrder.order_id, DBOrder.standing_quantity)
                .where(
                    (DBOrder.user_id == user_id) 
                    & (DBOrder.ticker == message.ticker) 
                    & (
                        (DBOrder.order_status == OrderStatus.FILLED) |
                        (DBOrder.order_status == OrderStatus.PARTIALLY_CLOSED_ACTIVE)
                    )
                    & (DBOrder.market_type == message.market_type)
                )
            )
            
            all_orders = r.all()
        
        if not all_orders:
            raise InvalidAction("Insufficient assets to perform action")

        target_quantity = message.quantity
        order_ids = []
        
        for o in all_orders:
            target_quantity -= o[1]
            order_ids.append(str(o[0]))
        
        final_dict = message.model_dump()
        final_dict.update({
            'order_ids': order_ids,
            'price': self._ticker_quotes[message.ticker]
        })
        return final_dict
    
    async def _modify_order_handler(self, message: ModifyOrder, user_id: str) -> dict:
        async with get_db_session() as session:
            result = await session.execute(
                select(DBOrder.order_status, DBOrder.ticker)
                .where(
                    (DBOrder.user_id == user_id)
                    & (DBOrder.order_id == message.order_id)
                    & (DBOrder.order_status != OrderStatus.CLOSED)
                    & (DBOrder.market_type == message.market_type)
                )
            )
            
            order_details = result.first()
        
        if not order_details:
            raise InvalidAction
        
        final_dict = message.model_dump()
        final_dict.update({
            'order_status': order_details[0], 
            'order_id': str(final_dict['order_id']),
            'ticker': order_details[1],
        })
        return final_dict
    