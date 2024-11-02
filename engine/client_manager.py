import asyncio
import json
import random
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from functools import wraps
from uuid import UUID

# FA
from fastapi import WebSocket
from pydantic import ValidationError

# SA
from sqlalchemy import insert, select, inspect

# Local
from config import REDIS_CONN_POOL, REDIS_CLIENT
from db_models import Orders, Users
from enums import OrderType
from models import OrderRequest
from utils.db import get_db_session


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
            await self.socket.close(code=1014, reason="Invalid Schema")
        except Exception as e:
            print(type(e), str(e), end="***---***")
    return handle_exceptions


class ClientManager:
    def __init__(self, websocket: WebSocket):
        self.socket = websocket
        # self.pubsub = REDIS_CLIENT.pubsub()

        self.bids: dict[float, list[OrderRequest]] = defaultdict(list)
        self.asks: dict[float, list[OrderRequest]] = defaultdict(list)
        self.ticker_quotes: dict[str, float] = defaultdict(float)


    @websocket_exception_handler
    async def connect(self) -> None:
        await self.socket.accept()


    @websocket_exception_handler
    async def receive(self) -> None:
        """
        Funnels the order request
        :return:
        """

        # Initially verifying the user exists
        message = await self.socket.receive_text()
        message = json.loads(message)
        if not await self.check_if_user_exists(message):
            await self.socket.close(code=1008, reason="User doesn't exist")
            raise Exception("Websocket closed")

        await self.socket.send_text(json.dumps({'message': 'success'}))

        tasks = [
            self.listen_to_prices(),
            self.handle_incoming_requests(),
            self.listen_to_updates(),
        ]

        await asyncio.gather(*tasks)


    async def handle_incoming_requests(self):
        """
        Filters and cleans incoming request
        before sending off to the orderbook & matching engine
        for facilitation
        :return:
        """
        while True:
            message = await self.socket.receive_text()
            message = OrderRequest(**json.loads(message))

            if message.type == OrderType.MARKET or message.type == OrderType.LIMIT:
                order = await self.create_order_in_db(message)
            else:
                order = message.dict()

            order.update({'user_id': self.user_id})
            asyncio.create_task(self.send_to_engine(order))


    async def check_if_user_exists(self, message: dict) -> bool:
        """
        Checks if the user id is in the database
        :param message:
        :return: True if the user exists, else False
        """
        try:
            async with get_db_session() as session:
                result = await session.execute(
                    select(Users.user_id).where(Users.user_id == UUID(message.get('user_id'))))
                user_id = result.scalar()
                if user_id:
                    self.user_id = user_id
                    return True
                return False
        except Exception as e:
            print(type(e), str(e))
            pass


    @websocket_exception_handler
    async def send_to_engine(self, order: dict) -> None:
        """
        Forwards order data to the matching engine
        :param order:
        :return:
        """
        order = {
            k: (str(v) if isinstance(v, UUID) else v)
            for k, v in order.items()
        }

        for k, v in order.items():
            if isinstance(v, dict):
                for key, value in order[k].items():
                    if isinstance(value, UUID):
                        order[k][key] = str(value)

        await REDIS_CLIENT.publish(channel="to_order_book", message=json.dumps(order))


    async def create_order_in_db(self, message: OrderRequest) -> dict:
        """
        Saves the order in the DB
        :param message:
        :return:
        """
        try:
            if message.limit_order:
                data = message.limit_order
            if message.market_order:
                data = message.market_order

            price = None
            while not price:
                price = self.ticker_quotes.get(data.ticker, None)
                await asyncio.sleep(0.1)

            data = data.dict()
            if data.get('stop_loss', None):
                data['stop_loss'] = data.get('stop_loss', {}).get('price', None)

            if data.get('take_profit', None):
                data['take_profit'] = data.get('take_profit', {}).get('price', None)

            async with get_db_session() as session:
                result = await session.execute(
                    insert(Orders)
                    .values(
                        **data,
                        user_id=self.user_id,
                        order_type=message.type,
                        price=round(random.uniform(100, 150), 2),  # price
                    )
                    .returning(Orders)
                )
                o = result.scalar()
                return {
                    k: (str(v) if isinstance(v, (datetime, UUID)) else v)
                    for k, v in vars(o).items()
                    if k != '_sa_instance_state'
                }
        except Exception as e:
            print("[SAVE ORDER IN DB][ERROR] >> ", type(e), str(e))
            raise Exception


    async def listen_to_prices(self) -> None:
        """
        Subscribes to pubsub channel and
        stores the price in dictionary
        :return:
        """

        try:
            # with await REDIS_CONN_POOL.pubsub() as pubsub:
            async with REDIS_CLIENT.pubsub() as pubsub:
                await pubsub.subscribe('prices')
                async for message in pubsub.listen():
                    if message.get('type', None) == 'message':
                        self.ticker_quotes.update(
                            {
                                k: v for
                                k, v in json.loads(message.get('data').decode()).items()
                            }
                        )
        except Exception as e:
            print(type(e), str(e))
            pass


    async def listen_to_updates(self):
        """
            Subscribes to pubsub channel and relays updates
            back to client
        :return:
        """
        async with REDIS_CLIENT.pubsub() as pubsub:
            await pubsub.subscribe(f"trades_{self.user_id}")
            async for message in pubsub.listen():
                if message.get('type', None) == 'message':
                    await self.socket.send_bytes(message['data'])
                    print('sent client message')
