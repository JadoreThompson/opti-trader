import asyncio
import random
from faker import Faker
from uuid import UUID
import websockets

# Local
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from enums import MarketType, OrderType, Side
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
        make_limit = random.choice([True, False])
        
        data = {
            'market_type': MarketType.FUTURES,
            'type': OrderType.MARKET,
            'ticker': 'APPL',
            'quantity': random.randint(10, 15),
            'take_profit': None,
            'stop_loss': None,
            'limit_price': None,
            'side': random.choice([Side.LONG, Side.SHORT])
        }
        
        if make_limit:
            data['type'] = OrderType.LIMIT
            data['limit_price'] = random.choice([i for i in range(10, 210, 10)])
            
        orders.append(data)
        
    return orders


# Tests
# ^^^^^
import json

async def create_user():
    async with get_db_session() as sess:
        pw = fkr.pystr()
        creds = {'email': fkr.email(), 'password': pw, 'username': fkr.last_name(), 'visible': random.choice([True, False])}
        # with open('myfile.txt', 'w') as f:
        #     f.write(f'Password: {pw}\n')
        #     f.write(f'{creds}')
        
        user = await sess.execute(
            sa.insert(Users)
            .values(**creds, authenticated=True)
            .returning(Users)
        )

        await sess.commit()
        user = user.scalar()
        return user, create_jwt_token({'sub': str(user.user_id)})


async def listen_to_socket(websocket, box):
    while True:
        m = await websocket.recv()
        try:
            m = json.loads(m)
            if m.get('category', None) == 'success':
                if (oid := m.get('details', {}).get('order_id', None)):
                    box.append(oid)
        except json.JSONDecodeError:
            pass
        await asyncio.sleep(1)


async def push_to_socket(websocket, orders, divider, close_quantity, counter, box):
    while counter < len(orders):
        await websocket.send(json.dumps(orders[counter]))
        
        if divider > 1 and counter > 0:
            if counter % divider == 0:
                try:
                    await websocket.send(json.dumps({
                        'type': OrderType.CLOSE,
                        'market_type': MarketType.FUTURES,
                        'order_id': box.pop(),
                        'quantity': close_quantity,
                    }))
                except IndexError:
                    pass
        counter += 1
        await asyncio.sleep(1)


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
    _, token = await create_user()
    orders = await generate_order_requests(num_orders)
    box: list = []
    
    # print(f'trades_{_.user_id}')
    
    if kwargs.get('name', None):
        print(f'{num_orders} orders in queue for {kwargs['name']}')
    
    counter = 0
    
    while True:
        try:
            async with websockets.connect(SOCKET_URL) as websocket:
                await websocket.send(json.dumps({'token': token}))
                m = await websocket.recv()
                
                if 'name' in kwargs:
                    print(f'[{kwargs['name']}]: ', m)
                
                await asyncio.gather(*[
                    push_to_socket(
                        websocket,
                        orders,
                        divider,
                        close_quantity,
                        counter,
                        box,
                    ), 
                    listen_to_socket(websocket, box)
                ])
                    
        except websockets.exceptions.ConnectionClosedError:
            if kwargs.get('name', None):
                print(f'[{kwargs['name']}] Reconnecting - Count={counter}')
            
            await asyncio.sleep(1)

from random import randint

async def main():
    global TEST_SIZE
    
    await asyncio.gather(*[
        test_socket(
            name=fkr.first_name(), 
            divider=randint(2, 5), 
            num_orders=randint(10_000, 30_000), 
            close_quantity=randint(50, 100)
        ) for _ in range(TEST_SIZE)
    ])

# Begins to throw issues above 2
TEST_SIZE = 5
asyncio.run(main())
