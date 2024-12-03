import asyncio
import random
from faker import Faker
from uuid import UUID
import websockets

# Local
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from enums import OrderType
from config import PH
from db_models import Base, Users
from models import socket_models
from utils.auth import create_jwt_token
from utils.db import get_db_session

# SA
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


# Envs
# ^^^^
fkr = Faker()
SOCKET_URL = 'ws://127.0.0.1:8000/stream/trade'


# Funcs
# ^^^^^
async def generate_order_requests(quantity: int = 10) -> list:
    orders = []
    
    for _ in range(quantity):
        order_obj = random.choice([
            socket_models.MarketOrder(
                ticker='APPL',
                quantity=random.randint(1, 50),
            ),
            
            socket_models.LimitOrder(
                ticker='APPL',
                quantity=random.randint(1, 50),
                limit_price=random.choice([n for n in range(20, 1000, 10)])
            )
        ])

        order_type = {
            socket_models.MarketOrder: OrderType.MARKET,
            socket_models.LimitOrder: OrderType.LIMIT
        }[type(order_obj)]
            
        order_req = socket_models.OrderRequest(
            type=order_type, 
            market_order=order_obj if order_type == OrderType.MARKET else None,
            limit_order=order_obj if order_type == OrderType.LIMIT else None
        )
        orders.append(order_req)
        
    return orders


# Tests
# ^^^^^
import json

async def test_create_user():
    async with get_db_session() as sess:
        pw = fkr.pystr()
        creds = {'email': fkr.email(), 'password': PH.hash(pw)}
        # with open('myfile.txt', 'w') as f:
        #     f.write(f'Password: {pw}\n')
        #     f.write(f'{creds}')
        
        user = await sess.execute(
            sa.insert(Users)
            .values(**creds)
            .returning(Users)
        )

        await sess.commit()
        user = user.scalar()
        return user, create_jwt_token({'sub': str(user.user_id)})


async def test_socket(
    divider: int = None,
    close_quantity: int = 20,
    num_orders: int = 100,
    **kwargs
):
    """
    Connects to socket and creates orders
    
    Args:
        divider (int, optional): How often to sell. Defaults to 5.
        quantity (int, optional): Quantity of shares to purchase. Defaults to 20.
    """
    _, token = await test_create_user()
    orders = await generate_order_requests(num_orders)
    
    if kwargs.get('name', None):
        print(f'{num_orders} orders in queue for {kwargs['name']}')
    
    i = 0
    while i < len(orders):
        try:
            async with websockets.connect(SOCKET_URL) as socket:
                await socket.send(json.dumps({'token': token}))
                m = await socket.recv()
                print('Signing Message: ', m)
                
                while i < len(orders):
                    await socket.send(json.dumps(orders[i].model_dump()))
                    
                    if divider and i > 0:
                        if i % divider == 0:
                            await socket.send(json.dumps({
                                'type': OrderType.CLOSE,
                                'close_order': {
                                    'quantity': close_quantity,
                                    'ticker': 'APPL'
                                }
                            }))
                    await asyncio.sleep(1)
                    i += 1
        except websockets.exceptions.ConnectionClosedError:
                    if kwargs.get('name', None):
                        print(f'[{kwargs['name']}] Disconnect - {i}')

from random import randint

async def main():
    global TEST_SIZE
    
    await asyncio.gather(*[
        test_socket(
            name=fkr.first_name(), 
            divider=randint(2, 5), 
            num_orders=randint(10_000, 30_000), 
            close_quantity=randint(10, 50)
        ) for _ in range(TEST_SIZE)
    ])

# Begins to throw issues above 2
TEST_SIZE = 5
asyncio.run(main())
